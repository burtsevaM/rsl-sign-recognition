"""FastAPI application factory for the clean runtime shell."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from rsl_sign_recognition.api.routes.probes import router as probes_router
from rsl_sign_recognition.runtime.config import RuntimeShellSettings
from rsl_sign_recognition.runtime.services import RuntimeServiceRegistry
from rsl_sign_recognition.runtime.shell import RuntimeShell


def create_app(
    *,
    settings: RuntimeShellSettings | None = None,
    services: RuntimeServiceRegistry | None = None,
) -> FastAPI:
    """Create a minimal FastAPI runtime shell with honest readiness probes."""

    resolved_settings = settings or RuntimeShellSettings.from_env()
    resolved_services = services or RuntimeServiceRegistry.build(resolved_settings)
    runtime_shell = RuntimeShell(
        settings=resolved_settings,
        services=resolved_services,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime_shell = runtime_shell
        yield

    app = FastAPI(
        title="RSL Sign Recognition Runtime Shell",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(probes_router)
    return app
