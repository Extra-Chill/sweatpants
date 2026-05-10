"""Bearer token authentication for the Sweatpants API.

Sweatpants accepts two kinds of `Authorization: Bearer <token>` credentials:

1.  **Master token** (`SWEATPANTS_API_AUTH_TOKEN`)

    Full admin access to every endpoint. Used by orchestration callers
    (CLI, ops scripts, trusted server-side code). Static, no expiry.

2.  **Signed token** (HMAC-SHA256 over `SWEATPANTS_API_SIGNED_TOKEN_SECRET`)

    Short-lived, user-scoped, capability-scoped. Minted by a trusted
    issuer (e.g. a WordPress plugin signing a token for an authenticated
    user via the same shared secret). Format:

        <base64url(payload_json)>.<base64url(hmac_sha256(secret, payload_b64))>

    Where `payload_json` is a UTF-8 JSON object with at least:

        {
          "iss": "<issuer-id>",      # opaque issuer identifier
          "sub": <user-id-int>,      # subject — the user the token represents
          "scope": "<space-separated-scopes>",
          "exp": <unix-timestamp>,   # expiry; rejected if past
          "jti": "<uuid4-hex>"       # token id, reserved for revocation lists
        }

    The signature is computed over the base64url-encoded payload string
    (NOT the decoded JSON) so issuers and validators agree byte-for-byte
    regardless of JSON whitespace.

Both credentials are optional in config — if neither is set, the server
refuses every request. There is no anonymous mode.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from sweatpants.config import get_settings


MASTER_PRINCIPAL_SUB = 0
MASTER_SCOPE = "*"


@dataclass(frozen=True)
class AuthPrincipal:
    kind: str  # "master" | "signed"
    sub: int
    scopes: tuple[str, ...]
    expires_at: Optional[int] = None
    issuer: Optional[str] = None
    token_id: Optional[str] = None

    def has_scope(self, required: str) -> bool:
        if MASTER_SCOPE in self.scopes:
            return True
        return required in self.scopes


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": 'Bearer realm="sweatpants"'},
    )


def _b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"invalid base64url: {exc}") from exc


def _verify_signed_token(token: str, secret: str) -> AuthPrincipal:
    rsplit_idx = token.rfind(".")
    if rsplit_idx <= 0 or rsplit_idx == len(token) - 1:
        raise _unauthorized("malformed token")

    payload_b64 = token[:rsplit_idx]
    sig_b64 = token[rsplit_idx + 1 :]

    try:
        provided_sig = _b64url_decode(sig_b64)
    except ValueError:
        raise _unauthorized("malformed token")

    expected_sig = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise _unauthorized("invalid signature")

    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        raise _unauthorized("malformed payload")

    if not isinstance(payload, dict):
        raise _unauthorized("malformed payload")

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or exp <= time.time():
        raise _unauthorized("token expired")

    sub = payload.get("sub")
    if not isinstance(sub, int) or sub <= 0:
        raise _unauthorized("missing or invalid subject")

    scope_str = payload.get("scope", "")
    if not isinstance(scope_str, str):
        raise _unauthorized("invalid scope")
    scopes = tuple(s for s in scope_str.split() if s)
    if not scopes:
        raise _unauthorized("token has no scopes")

    issuer = payload.get("iss") if isinstance(payload.get("iss"), str) else None
    token_id = payload.get("jti") if isinstance(payload.get("jti"), str) else None

    return AuthPrincipal(
        kind="signed",
        sub=sub,
        scopes=scopes,
        expires_at=int(exp),
        issuer=issuer,
        token_id=token_id,
    )


def get_auth_principal(
    authorization: Optional[str] = Header(default=None),
) -> AuthPrincipal:
    """FastAPI dependency: resolve the Authorization header to a principal."""
    if not authorization:
        raise _unauthorized("missing Authorization header")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise _unauthorized("Authorization must be Bearer")

    token = parts[1].strip()

    settings = get_settings()
    master = settings.api_auth_token
    secret = settings.api_signed_token_secret

    if master and hmac.compare_digest(master, token):
        return AuthPrincipal(
            kind="master",
            sub=MASTER_PRINCIPAL_SUB,
            scopes=(MASTER_SCOPE,),
        )

    if secret:
        return _verify_signed_token(token, secret)

    raise _unauthorized("invalid credentials")


def require_scope(scope: str):
    """FastAPI dependency factory: require a specific scope on the principal."""

    def _checker(
        principal: AuthPrincipal = Depends(get_auth_principal),
    ) -> AuthPrincipal:
        if not principal.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"token missing required scope: {scope}",
            )
        return principal

    return _checker
