"""Tests for proxy client module."""

import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from sweatpants.proxy.client import build_proxy_url, get_proxy_url, proxied_request


@pytest.fixture(autouse=True)
def set_test_credentials(monkeypatch):
    """Set test credentials for all tests."""
    monkeypatch.setenv("SWEATPANTS_BRIGHTDATA_USERNAME", "test-user")
    monkeypatch.setenv("SWEATPANTS_BRIGHTDATA_PASSWORD", "test-pass")
    monkeypatch.setenv("SWEATPANTS_BRIGHTDATA_HOST", "proxy.test.com")
    monkeypatch.setenv("SWEATPANTS_BRIGHTDATA_PORT", "12345")


class TestBuildProxyUrl:
    """Tests for build_proxy_url function."""

    def test_basic_url_structure(self):
        """URL should have correct structure with credentials."""
        url = build_proxy_url()
        assert url.startswith("http://test-user-session-")
        assert ":test-pass@proxy.test.com:12345" in url

    def test_session_id_none_generates_uuid(self):
        """None session_id should generate unique session each call."""
        url1 = build_proxy_url(session_id=None)
        url2 = build_proxy_url(session_id=None)
        assert url1 != url2  # Different UUIDs

    def test_session_id_sticky(self):
        """Same session_id should produce same session in URL."""
        url1 = build_proxy_url(session_id="my-session")
        url2 = build_proxy_url(session_id="my-session")
        assert "session-my-session" in url1
        assert "session-my-session" in url2

    def test_geo_country_code(self):
        """Two-letter geo should be treated as country."""
        url = build_proxy_url(geo="us")
        assert "-country-us" in url

    def test_geo_city_name(self):
        """Longer geo without dash should be treated as city."""
        url = build_proxy_url(geo="newyork")
        assert "-city-newyork" in url

    def test_geo_state_format(self):
        """Geo with dash should be country-state."""
        url = build_proxy_url(geo="us-ny")
        assert "-country-us" in url
        assert "-state-ny" in url

    def test_combined_session_and_geo(self):
        """Session and geo should both appear in URL."""
        url = build_proxy_url(session_id="test", geo="newyork")
        assert "-session-test" in url
        assert "-city-newyork" in url


class TestBuildProxyUrlMissingCredentials:
    """Tests for missing credential handling."""

    def test_missing_username_raises(self, monkeypatch):
        """Missing username should raise RuntimeError."""
        monkeypatch.delenv("SWEATPANTS_BRIGHTDATA_USERNAME", raising=False)
        monkeypatch.setenv("SWEATPANTS_BRIGHTDATA_USERNAME", "")
        with pytest.raises(RuntimeError, match="Bright Data proxy not configured"):
            build_proxy_url()

    def test_missing_password_raises(self, monkeypatch):
        """Missing password should raise RuntimeError."""
        monkeypatch.delenv("SWEATPANTS_BRIGHTDATA_PASSWORD", raising=False)
        monkeypatch.setenv("SWEATPANTS_BRIGHTDATA_PASSWORD", "")
        with pytest.raises(RuntimeError, match="Bright Data proxy not configured"):
            build_proxy_url()


class TestGetProxyUrl:
    """Tests for get_proxy_url convenience function."""

    def test_returns_rotating_url(self):
        """get_proxy_url should return a new URL each time."""
        url1 = get_proxy_url()
        url2 = get_proxy_url()
        assert url1 != url2  # Different sessions = different URLs


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
    async def test_passes_session_and_geo(self):
        """session_id and geo should affect proxy URL."""
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
                geo="newyork",
            )

            call_kwargs = mock_client.call_args.kwargs
            proxy_url = call_kwargs["proxy"]
            assert "-session-sticky" in proxy_url
            assert "-city-newyork" in proxy_url
