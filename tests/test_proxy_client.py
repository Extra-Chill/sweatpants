"""Tests for proxy client module."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from sweatpants.proxy.client import build_proxy_url, get_proxy_url, proxied_request


@pytest.fixture(autouse=True)
def set_test_credentials(monkeypatch):
    """Set test proxy URL for all tests."""
    monkeypatch.setenv("SWEATPANTS_PROXY_URL", "http://user:pass@proxy.test.com:12345")
    monkeypatch.setenv(
        "SWEATPANTS_PROXY_ROTATION_URL",
        "http://user-session-{session}:pass@proxy.test.com:12345",
    )


class TestBuildProxyUrl:
    """Tests for build_proxy_url function."""

    def test_returns_base_url_without_session(self):
        """Without session_id, should return base proxy URL."""
        url = build_proxy_url()
        assert url == "http://user:pass@proxy.test.com:12345"

    def test_returns_base_url_with_session_but_no_rotation_url(self, monkeypatch):
        """With session but no rotation URL, should return base URL."""
        monkeypatch.setenv("SWEATPANTS_PROXY_ROTATION_URL", "")
        url = build_proxy_url(session_id="my-session")
        assert url == "http://user:pass@proxy.test.com:12345"

    def test_returns_rotation_url_with_session(self):
        """With session and rotation URL, should substitute session placeholder."""
        url = build_proxy_url(session_id="my-session")
        assert url == "http://user-session-my-session:pass@proxy.test.com:12345"

    def test_session_placeholder_replacement(self):
        """Session placeholder should be replaced correctly."""
        url = build_proxy_url(session_id="sticky-123")
        assert "{session}" not in url
        assert "sticky-123" in url


class TestBuildProxyUrlMissingCredentials:
    """Tests for missing credential handling."""

    def test_missing_proxy_url_raises(self, monkeypatch):
        """Missing proxy URL should raise RuntimeError."""
        monkeypatch.setenv("SWEATPANTS_PROXY_URL", "")
        with pytest.raises(RuntimeError, match="Proxy not configured"):
            build_proxy_url()


class TestGetProxyUrl:
    """Tests for get_proxy_url convenience function."""

    def test_returns_base_url(self):
        """get_proxy_url should return the base proxy URL."""
        url = get_proxy_url()
        assert url == "http://user:pass@proxy.test.com:12345"


class TestProxiedRequest:
    """Tests for proxied_request function."""

    @pytest.mark.asyncio
    async def test_makes_request_through_proxy(self):
        """Request should use proxy URL."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.text = "test response"
        mock_response.status_code = 200
        mock_response.headers = {}

        with patch("sweatpants.proxy.client.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            response = await proxied_request("GET", "https://example.com")

            # Verify proxy was configured
            call_kwargs = mock_client.call_args.kwargs
            assert "proxy" in call_kwargs
            assert "proxy.test.com:12345" in call_kwargs["proxy"]

    @pytest.mark.asyncio
    async def test_browser_mode_adds_headers(self):
        """browser_mode=True should add browser headers."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.text = "test"
        mock_response.status_code = 200

        with patch("sweatpants.proxy.client.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            await proxied_request("GET", "https://example.com", browser_mode=True)

            call_args = mock_instance.request.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "User-Agent" in headers
            assert "Mozilla" in headers["User-Agent"]

    @pytest.mark.asyncio
    async def test_passes_session_id(self):
        """session_id should affect proxy URL when rotation URL configured."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.text = "test"
        mock_response.status_code = 200

        with patch("sweatpants.proxy.client.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            await proxied_request(
                "GET",
                "https://example.com",
                session_id="sticky",
            )

            call_kwargs = mock_client.call_args.kwargs
            proxy_url = call_kwargs["proxy"]
            assert "session-sticky" in proxy_url
