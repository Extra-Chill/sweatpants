"""Sweatpants - Server-side automation engine for long-running tasks."""

__version__ = "0.3.2"

from sweatpants.sdk.module import Module
from sweatpants.sdk.callback import send_signed_callback, sign_callback_token
from sweatpants.proxy.client import proxied_request
from sweatpants.browser.pool import get_browser

__all__ = [
    "Module",
    "send_signed_callback",
    "sign_callback_token",
    "proxied_request",
    "get_browser",
    "__version__",
]
