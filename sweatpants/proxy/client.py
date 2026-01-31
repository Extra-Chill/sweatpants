"""HTTP client with rotating proxy support."""

from typing import Any, Optional

import httpx

from sweatpants.config import get_settings

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


def build_proxy_url(session_id: Optional[str] = None) -> str:
    """Build proxy URL, optionally with session for sticky IP.

    Args:
        session_id: Session identifier for sticky IP. None = new IP each request.

    Returns:
        Proxy URL for use with HTTP clients.

    Raises:
        RuntimeError: If proxy URL not configured.
    """
    settings = get_settings()

    if not settings.proxy_url:
        raise RuntimeError("Proxy not configured. Set SWEATPANTS_PROXY_URL.")

    # If rotation URL provided and session requested, use rotation format
    if session_id and settings.proxy_rotation_url:
        return settings.proxy_rotation_url.replace("{session}", session_id)

    # Otherwise return base URL (new IP each request for most providers)
    return settings.proxy_url


def get_proxy_url() -> str:
    """Get a rotating proxy URL (new IP each call)."""
    return build_proxy_url()


async def proxied_request(
    method: str,
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, Any]] = None,
    data: Optional[dict[str, Any]] = None,
    json: Optional[dict[str, Any]] = None,
    timeout: Optional[float] = None,
    browser_mode: bool = False,
    session_id: Optional[str] = None,
) -> httpx.Response:
    """Make HTTP request through rotating proxy.

    Args:
        method: HTTP method
        url: Target URL
        headers: Request headers
        params: Query parameters
        data: Form data
        json: JSON body
        timeout: Request timeout
        browser_mode: Add realistic browser headers
        session_id: Sticky session ID (None = new IP each request)

    Returns:
        httpx.Response
    """
    proxy_url = build_proxy_url(session_id=session_id)

    request_headers = headers.copy() if headers else {}
    if browser_mode:
        for key, value in BROWSER_HEADERS.items():
            if key not in request_headers:
                request_headers[key] = value

    kwargs: dict[str, Any] = {"headers": request_headers} if request_headers else {}
    if params:
        kwargs["params"] = params
    if data:
        kwargs["data"] = data
    if json:
        kwargs["json"] = json
    if timeout:
        kwargs["timeout"] = timeout

    async with httpx.AsyncClient(
        proxy=proxy_url,
        timeout=httpx.Timeout(timeout or 30.0),
        follow_redirects=True,
        verify=False,  # Many proxy providers use self-signed certificates
    ) as client:
        return await client.request(method, url, **kwargs)
