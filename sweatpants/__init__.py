"""Sweatpants - Server-side automation engine for long-running tasks."""

__version__ = "0.2.5"

from sweatpants.sdk.module import Module
from sweatpants.proxy.client import proxied_request
from sweatpants.browser.pool import get_browser

__all__ = ["Module", "proxied_request", "get_browser", "__version__"]
