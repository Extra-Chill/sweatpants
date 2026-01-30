"""HTTP client with rotating proxy support."""

from typing import Any, Optional

import httpx

from sweatpants.config import get_settings

_client: Optional[httpx.AsyncClient] = None


async def get_proxy_config() -> dict[str, Any]:
    """Get proxy configuration from the rotating proxy service.

    Returns:
        dict with proxy URL and configuration
    """
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{settings.proxy_service_url}/proxy")
        response.raise_for_status()
        return response.json()


async def _get_client() -> httpx.AsyncClient:
    """Get or create the HTTP client with proxy configuration."""
    global _client

    if _client is None:
        settings = get_settings()

        try:
            config = await get_proxy_config()
            proxy_url = config.get("proxy_url")
            _client = httpx.AsyncClient(
                proxy=proxy_url,
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
        except Exception:
            _client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )

    return _client


async def proxied_request(
    method: str,
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, Any]] = None,
    data: Optional[dict[str, Any]] = None,
    json: Optional[dict[str, Any]] = None,
    timeout: Optional[float] = None,
) -> httpx.Response:
    """Make an HTTP request through the rotating proxy.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: Target URL
        headers: Optional request headers
        params: Optional query parameters
        data: Optional form data
        json: Optional JSON body
        timeout: Optional request timeout in seconds

    Returns:
        httpx.Response object
    """
    client = await _get_client()

    kwargs: dict[str, Any] = {}
    if headers:
        kwargs["headers"] = headers
    if params:
        kwargs["params"] = params
    if data:
        kwargs["data"] = data
    if json:
        kwargs["json"] = json
    if timeout:
        kwargs["timeout"] = timeout

    return await client.request(method, url, **kwargs)


async def close_client() -> None:
    """Close the HTTP client."""
    global _client
    if _client:
        await _client.aclose()
        _client = None
