"""FastAPI application factory."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sweatpants.api.scheduler import get_scheduler
from sweatpants.browser.pool import shutdown_pool
from sweatpants.config import get_settings
from sweatpants.engine.module_loader import ModuleLoader
from sweatpants.proxy.client import build_proxy_url


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    try:
        proxy_url = build_proxy_url()
        proxy_host = proxy_url.split("@")[1] if "@" in proxy_url else proxy_url
        print(f"Proxy configured: {proxy_host}")
    except RuntimeError as e:
        print(f"Warning: {e} (modules requiring proxy will fail at runtime)")

    loader = ModuleLoader()
    discovered = await loader.discover_modules()
    if discovered > 0:
        print(f"Auto-installed {discovered} discovered module(s)")

    sched = get_scheduler()
    resumed = await sched.resume_interrupted_jobs()
    if resumed > 0:
        print(f"Resumed {resumed} interrupted job(s)")

    yield

    await shutdown_pool()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from sweatpants.api.routes import router

    settings = get_settings()

    app = FastAPI(
        title="Sweatpants",
        description="Server-side automation engine for long-running tasks",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware. Registered only when an allowlist is configured —
    # an empty allowlist preserves the pre-CORS behavior (no middleware,
    # no preflight handling, no Access-Control-Allow-Origin headers) so
    # headless server-to-server callers keep working unchanged.
    #
    # `allow_origins` is a strict allowlist (no wildcard support here);
    # signed bearer tokens carry user identity inside the JWT-shaped
    # payload, and a wide-open `*` would let any domain harvest tokens
    # and replay them inside their TTL. Operators who want a wildcard
    # can still configure `["*"]` explicitly via the env var.
    if settings.api_cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.api_cors_allow_origins,
            allow_credentials=settings.api_cors_allow_credentials,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
            max_age=settings.api_cors_max_age,
        )

    app.include_router(router)

    return app
