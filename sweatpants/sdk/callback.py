"""Signed-callback SENDER primitive for Sweatpants modules.

Sweatpants core already owns the INBOUND side of the signed-callback contract:

- ``sweatpants/api/auth.py`` (`_verify_signed_token`) verifies an
  ``Authorization: Bearer <token>`` HMAC-SHA256 signed token.
- ``sweatpants/api/routes.py`` exposes the ``POST /callbacks`` receiver.

What core LACKED is the symmetric OUTBOUND side: a module POSTing an
HMAC-signed completion callback OUT to an external receiver (e.g. a WordPress
plugin). Modules previously rolled their own inline ``base64``/``hashlib``/
``hmac``/``urllib`` POST, which is exactly how subtle auth bugs spread across
copies. This module centralizes that crypto + HTTP so every consumer shares
one audited implementation.

Token format (intentionally identical to core's ``_verify_signed_token`` and
to the WordPress ``wp_native_auth_verify_external_token`` verifier)::

    <base64url(payload_json)>.<base64url(hmac_sha256(secret, payload_b64))>

The signature is computed over the base64url-encoded payload STRING (not the
decoded JSON) so issuers and validators agree byte-for-byte regardless of JSON
whitespace. base64url is emitted WITHOUT ``=`` padding; the core verifier
re-pads before decoding, so unpadded round-trips cleanly.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Any, Awaitable, Callable, Optional


# Fixed scope minted into callback tokens. Receivers may gate on this so a
# callback token cannot be replayed against a different capability surface.
CALLBACK_SCOPE = "callback:write"

# Callbacks should be near-instant; a short TTL bounds replay exposure.
DEFAULT_CALLBACK_TTL_SECONDS = 300

# Best-effort single POST timeout (seconds).
DEFAULT_CALLBACK_TIMEOUT_SECONDS = 30


def _b64url_encode(raw: bytes) -> str:
    """Encode bytes as base64url WITHOUT padding (matches sweatpants core)."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def sign_callback_token(
    secret: str,
    *,
    issuer: str = "sweatpants",
    user_id: Optional[int] = None,
    job_id: Optional[str] = None,
    scope: str = CALLBACK_SCOPE,
    ttl_seconds: int = DEFAULT_CALLBACK_TTL_SECONDS,
) -> str:
    """Mint a sweatpants-compatible signed bearer token.

    The token round-trips with core's ``_verify_signed_token`` (see
    ``sweatpants/api/auth.py``) and with the WordPress
    ``wp_native_auth_verify_external_token`` verifier against the same shared
    HMAC secret.

    Token shape:
        ``<base64url(payload_json)>.<base64url(hmac_sha256(secret, payload_b64))>``

    Payload claims:
        iss     issuer string (default ``"sweatpants"``)
        sub     subject — typically the WP user_id who submitted the job;
                falls back to ``0`` when unknown (the master-principal sub)
        scope   ``"callback:write"`` — a fixed scope so receivers can gate
        exp     unix expiry, default now + 300s
        jti     unique token id, populated with the job_id for trace when set

    Args:
        secret: Shared HMAC-SHA256 secret. Must be non-empty.
        issuer: ``iss`` claim.
        user_id: ``sub`` claim. ``None`` is coerced to ``0``.
        job_id: ``jti`` claim, for receiver-side trace/correlation.
        scope: ``scope`` claim. Defaults to ``"callback:write"``.
        ttl_seconds: Seconds until ``exp``.

    Returns:
        The signed token string.

    Raises:
        ValueError: If ``secret`` is empty.
    """
    if not secret:
        raise ValueError("a non-empty secret is required to sign a callback token")

    payload = {
        "iss": issuer,
        "sub": int(user_id) if user_id is not None else 0,
        "scope": scope,
        "exp": int(time.time()) + int(ttl_seconds),
    }
    if job_id:
        payload["jti"] = str(job_id)

    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = _b64url_encode(payload_json.encode("utf-8"))
    sig = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    sig_b64 = _b64url_encode(sig)
    return f"{payload_b64}.{sig_b64}"


async def send_signed_callback(
    url: str,
    payload: dict[str, Any],
    secret: Optional[str],
    *,
    issuer: str = "sweatpants",
    user_id: Optional[int] = None,
    job_id: Optional[str] = None,
    timeout: int = DEFAULT_CALLBACK_TIMEOUT_SECONDS,
    log: Optional[Callable[..., Awaitable[None]]] = None,
) -> bool:
    """POST ``payload`` as JSON to ``url`` with an optional signed Bearer token.

    Best-effort delivery: a single POST with a bounded timeout. Failures are
    logged (when a ``log`` callable is supplied) at WARNING level but NEVER
    raised — callers can treat callback delivery as fire-and-forget and rely on
    the job result remaining authoritative.

    When ``secret`` is set, the request carries an
    ``Authorization: Bearer <signed_token>`` header with the same HMAC-SHA256
    shape sweatpants core uses for its own signed tokens, so the receiver can
    use one verifier for both auth and callbacks.

    Args:
        url: HTTP(S) endpoint to POST to.
        payload: JSON-serializable body. POSTed as-is.
        secret: Shared HMAC secret. ``None``/empty disables signing.
        issuer: ``iss`` claim in the signed token.
        user_id: ``sub`` claim — the user the callback represents.
        job_id: ``jti`` claim, for receiver-side correlation.
        timeout: Per-request timeout in seconds.
        log: Optional async logger ``async def log(message, level="INFO")``.

    Returns:
        ``True`` iff the receiver returned a 2xx status. Callers may use this
        signal to gate post-callback work (e.g. cleanup).
    """

    async def _emit(message: str, level: str = "INFO") -> None:
        if log is not None:
            try:
                await log(message, level)
            except Exception:  # pragma: no cover — logging must never fail the send
                pass

    try:
        body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        await _emit(f"Signed callback skipped (unserializable payload): {exc!r}", "WARNING")
        return False

    headers = {"Content-Type": "application/json"}
    if secret:
        try:
            token = sign_callback_token(
                secret,
                issuer=issuer,
                user_id=user_id,
                job_id=job_id,
            )
            headers["Authorization"] = f"Bearer {token}"
        except ValueError as exc:  # pragma: no cover — guarded above
            await _emit(f"Signed callback token mint failed: {exc!r}", "WARNING")

    await _emit(f"Firing signed callback → {url}")

    request = urllib.request.Request(
        url,
        data=body_bytes,
        headers=headers,
        method="POST",
    )

    def _do_request() -> tuple[int, str]:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return getattr(resp, "status", 200), ""
        except urllib.error.HTTPError as exc:
            detail = exc.read(1024).decode("utf-8", errors="replace") if exc.fp else ""
            return exc.code, detail

    try:
        status, detail = await asyncio.to_thread(_do_request)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        await _emit(f"Signed callback failed (network): {exc}", "WARNING")
        return False
    except Exception as exc:  # pragma: no cover — defensive
        await _emit(f"Signed callback failed (unexpected): {exc!r}", "WARNING")
        return False

    if 200 <= status < 300:
        await _emit(f"Signed callback acknowledged (HTTP {status})")
        return True

    await _emit(f"Signed callback returned HTTP {status}: {detail[:200]}", "WARNING")
    return False
