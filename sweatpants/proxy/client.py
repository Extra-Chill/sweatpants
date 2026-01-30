"""HTTP client with Bright Data rotating proxy."""

import uuid
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


def build_proxy_url(
    session_id: Optional[str] = None,
    geo: Optional[str] = None,
) -> str:
    """Build Bright Data proxy URL with optional session and geo-targeting.

    Args:
        session_id: Session identifier for sticky IP. None = random IP each request.
        geo: Geo-target location. Formats:
             - City: "newyork", "austin", "losangeles"
             - Country: "us", "uk", "de"
             - State: "us-ny", "us-tx", "us-ca"

    Returns:
        Proxy URL with embedded parameters.

    Raises:
        RuntimeError: If Bright Data credentials not configured.
    """
    settings = get_settings()
    if not settings.brightdata_username or not settings.brightdata_password:
        raise RuntimeError(
            "Bright Data proxy not configured. "
            "Set SWEATPANTS_BRIGHTDATA_USERNAME and SWEATPANTS_BRIGHTDATA_PASSWORD."
        )

    params = []

    effective_session = session_id if session_id else uuid.uuid4().hex
    params.append(f"session-{effective_session}")

    if geo:
        if "-" in geo:
            country, state = geo.split("-", 1)
            params.append(f"country-{country}")
            params.append(f"state-{state}")
        elif len(geo) == 2:
            params.append(f"country-{geo}")
        else:
            params.append(f"city-{geo}")

    username_with_params = f"{settings.brightdata_username}-{'-'.join(params)}"

    return (
        f"http://{username_with_params}:{settings.brightdata_password}"
        f"@{settings.brightdata_host}:{settings.brightdata_port}"
    )


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
    geo: Optional[str] = None,
) -> httpx.Response:
    """Make HTTP request through Bright Data proxy.

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
        geo: Geo-target location (city/country/state)

    Returns:
        httpx.Response
    """
    proxy_url = build_proxy_url(session_id=session_id, geo=geo)

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
        verify=False,  # Bright Data proxy uses self-signed certificates
    ) as client:
        return await client.request(method, url, **kwargs)
