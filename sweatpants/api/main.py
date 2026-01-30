"""FastAPI application factory."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from sweatpants.api.scheduler import get_scheduler
from sweatpants.browser.pool import shutdown_pool
from sweatpants.proxy.client import build_proxy_url


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    try:
        proxy_url = build_proxy_url()
        proxy_host = proxy_url.split("@")[1] if "@" in proxy_url else proxy_url
        print(f"Proxy configured: {proxy_host}")
    except RuntimeError as e:
        print(f"FATAL: {e}")
        raise

    sched = get_scheduler()
    resumed = await sched.resume_interrupted_jobs()
    if resumed > 0:
        print(f"Resumed {resumed} interrupted job(s)")

    yield

    await shutdown_pool()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from sweatpants.api.routes import router

    app = FastAPI(
        title="Sweatpants",
        description="Server-side automation engine for long-running tasks",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(router)

    return app
