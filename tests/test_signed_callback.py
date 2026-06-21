"""Tests for the signed-callback SENDER primitive.

The load-bearing guarantee is round-trip compatibility: a token minted by the
sender (:func:`sweatpants.sdk.callback.sign_callback_token`) MUST verify with
the existing inbound verifier (``sweatpants.api.auth._verify_signed_token``).
That verifier is the same shape the WordPress
``wp_native_auth_verify_external_token`` primitive validates, so proving the
round-trip here proves cross-host compatibility.
"""

from __future__ import annotations

import time

import pytest

from sweatpants.api.auth import _verify_signed_token
from sweatpants.sdk.callback import (
    CALLBACK_SCOPE,
    send_signed_callback,
    sign_callback_token,
)


SECRET = "shared-hmac-secret-for-callbacks"


def test_minted_token_verifies_with_inbound_verifier():
    token = sign_callback_token(
        SECRET,
        issuer="sweatpants",
        user_id=42,
        job_id="job-abc",
    )

    principal = _verify_signed_token(token, SECRET)

    assert principal.kind == "signed"
    assert principal.sub == 42
    assert CALLBACK_SCOPE in principal.scopes
    assert principal.issuer == "sweatpants"
    assert principal.token_id == "job-abc"
    assert principal.has_scope(CALLBACK_SCOPE)


def test_token_with_wrong_secret_is_rejected():
    token = sign_callback_token(SECRET, user_id=1, job_id="j")

    with pytest.raises(Exception):
        _verify_signed_token(token, "a-different-secret")


def test_empty_secret_raises():
    with pytest.raises(ValueError):
        sign_callback_token("", user_id=1)


def test_unpadded_base64url_round_trips():
    # The sender emits base64url WITHOUT '=' padding; the verifier re-pads.
    # Exercise a user_id whose payload length lands on a non-multiple-of-4
    # base64 boundary to prove the padding handling holds.
    token = sign_callback_token(SECRET, user_id=12345, job_id="x")
    assert "=" not in token.split(".")[0]
    principal = _verify_signed_token(token, SECRET)
    assert principal.sub == 12345


def test_expired_token_is_rejected():
    # ttl_seconds in the past -> exp already elapsed -> verifier rejects.
    token = sign_callback_token(SECRET, user_id=1, job_id="j", ttl_seconds=-10)
    with pytest.raises(Exception):
        _verify_signed_token(token, SECRET)


def test_default_user_id_is_zero_master_sub_but_verifier_requires_positive():
    # sub=0 is the master-principal sub; the signed-token verifier requires a
    # positive subject, so callbacks should always carry a real user_id. This
    # documents that contract rather than silently accepting sub=0.
    token = sign_callback_token(SECRET, job_id="j")  # user_id defaults to None -> 0
    with pytest.raises(Exception):
        _verify_signed_token(token, SECRET)


@pytest.mark.asyncio
async def test_send_signed_callback_best_effort_on_unreachable_host():
    # Best-effort contract: a network failure returns False, never raises.
    logs: list[tuple[str, str]] = []

    async def _log(message: str, level: str = "INFO") -> None:
        logs.append((message, level))

    # Reserved TEST-NET-1 address (RFC 5737) — guaranteed unroutable, fast-fail.
    ok = await send_signed_callback(
        "http://192.0.2.1:9/callback",
        {"hello": "world"},
        SECRET,
        user_id=7,
        job_id="net-fail",
        timeout=1,
        log=_log,
    )

    assert ok is False
    assert any(level == "WARNING" for _, level in logs)


@pytest.mark.asyncio
async def test_send_signed_callback_unserializable_payload_returns_false():
    ok = await send_signed_callback(
        "http://192.0.2.1:9/callback",
        {"bad": object()},  # not JSON-serializable
        SECRET,
        user_id=1,
    )
    assert ok is False
