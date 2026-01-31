"""Browser pool management with Playwright."""

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright

from sweatpants.config import get_settings
from sweatpants.proxy.client import build_proxy_url


class BrowserInstance:
    """A managed browser instance with lifecycle tracking."""

    def __init__(self, browser: Browser, created_at: datetime) -> None:
        self.browser = browser
        self.created_at = created_at
        self.use_count = 0

    @property
    def age_hours(self) -> float:
        """Get age of browser instance in hours."""
        delta = datetime.now(timezone.utc) - self.created_at
        return delta.total_seconds() / 3600

    def should_restart(self, max_hours: int) -> bool:
        """Check if browser should be restarted."""
        return self.age_hours >= max_hours


class BrowserPool:
    """Manages a pool of browser instances with automatic restart."""

    def __init__(self, geo: Optional[str] = None, use_proxy: bool = True) -> None:
        self.settings = get_settings()
        self._geo = geo
        self._use_proxy = use_proxy
        self._playwright: Optional[Playwright] = None
        self._browsers: list[BrowserInstance] = []
        self._available: asyncio.Queue[BrowserInstance] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._initialized = False

    async def start(self) -> None:
        """Initialize the browser pool."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            self._playwright = await async_playwright().start()

            for _ in range(self.settings.browser_pool_size):
                instance = await self._create_browser()
                self._browsers.append(instance)
                await self._available.put(instance)

            self._initialized = True

    async def _create_browser(self) -> BrowserInstance:
        """Create a new browser instance with optional proxy session."""
        if not self._playwright:
            raise RuntimeError("Playwright not initialized")

        launch_kwargs: dict[str, Any] = {"headless": True}

        if self._use_proxy:
            browser_session = f"browser-{uuid.uuid4()}"
            proxy_url = build_proxy_url(session_id=browser_session)
            launch_kwargs["proxy"] = {"server": proxy_url}

        browser = await self._playwright.chromium.launch(**launch_kwargs)
        return BrowserInstance(
            browser=browser,
            created_at=datetime.now(timezone.utc),
        )

    async def acquire(self) -> BrowserContext:
        """Acquire a browser context from the pool."""
        if not self._initialized:
            await self.start()

        instance = await self._available.get()
        instance.use_count += 1

        if instance.should_restart(self.settings.browser_restart_hours):
            await instance.browser.close()
            new_instance = await self._create_browser()

            idx = self._browsers.index(instance)
            self._browsers[idx] = new_instance
            instance = new_instance

        context = await instance.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        return context

    async def release(self, context: BrowserContext) -> None:
        """Release a browser context back to the pool."""
        await context.close()

        for instance in self._browsers:
            if not instance.browser.is_connected():
                continue

            contexts = instance.browser.contexts
            if len(contexts) == 0 or all(c != context for c in contexts):
                await self._available.put(instance)
                break

    async def stop(self) -> None:
        """Shut down the browser pool."""
        async with self._lock:
            for instance in self._browsers:
                try:
                    await instance.browser.close()
                except Exception:
                    pass

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            self._browsers.clear()
            self._initialized = False


_pools: dict[tuple[Optional[str], bool], BrowserPool] = {}


def _get_pool(geo: Optional[str] = None, use_proxy: bool = True) -> BrowserPool:
    """Get browser pool for the given geo-target and proxy setting."""
    key = (geo, use_proxy)
    if key not in _pools:
        _pools[key] = BrowserPool(geo=geo, use_proxy=use_proxy)
    return _pools[key]


@asynccontextmanager
async def get_browser(
    geo: Optional[str] = None,
    use_proxy: bool = True,
) -> AsyncIterator[BrowserContext]:
    """Get a browser context from the pool.

    Args:
        geo: Geo-target location (city/country/state). Default pool if None.
        use_proxy: Whether to route through proxy. Defaults to True.
            Set to False for sites that block known proxy IPs (e.g., Google).

    Usage:
        async with get_browser() as browser:
            page = await browser.new_page()
            await page.goto("https://example.com")

        async with get_browser(geo="newyork") as browser:
            page = await browser.new_page()
            await page.goto("https://example.com")  # NYC IP

        async with get_browser(use_proxy=False) as browser:
            page = await browser.new_page()
            await page.goto("https://google.com")  # Direct connection
    """
    pool = _get_pool(geo=geo, use_proxy=use_proxy)
    context = await pool.acquire()
    try:
        yield context
    finally:
        await pool.release(context)


async def shutdown_pool() -> None:
    """Shut down all browser pools."""
    for pool in _pools.values():
        await pool.stop()
    _pools.clear()
