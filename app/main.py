"""FastAPI application with hexagonal architecture and shared compute runtime.

This service is licensed under AGPL 3.0 due to the use of Kerykeion library.
Public repository: https://github.com/markymark2001/staia-astrology-service

The service is automatically synced from the private Staia repository.
"""

import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from app.api.v1 import api_router
from app.config.sentry_release import get_sentry_release
from app.config.settings import Settings, settings
from app.core.error_handlers import (
    handle_astrology_service_error,
    handle_chart_calculation_error,
    handle_generic_exception,
    handle_invalid_birth_data,
)
from app.core.exceptions import (
    AstrologyServiceException,
    ChartCalculationException,
    InvalidBirthDataException,
)
from app.infrastructure.compute_runtime import create_compute_runtime

logger = logging.getLogger(__name__)
SERVICE_ROLE = "astrology-service"
_PRIVATE_KEY_TERMS = ["forwarded", "-ip", "remote-", "via", "-user"]


def init_astrology_sentry(
    *,
    dsn: str,
    environment: str,
    release: str | None,
) -> None:
    """Initialize astrology-service Sentry with explicit issue ownership."""
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        traces_sample_rate=0.2,
        # Keep messages grouped by text, as before SDK 3 turned this on.
        attach_stacktrace=False,
        # Keeps what send_default_pii=False collected before SDK 3: no
        # request bodies (birth data), no user details, and no client IPs.
        # Frame variables keep the SDK's sensitive-key filtering.
        data_collection={
            "user_info": False,
            "http_bodies": [],
            "http_headers": {"request": {"mode": "denylist", "terms": _PRIVATE_KEY_TERMS}},
            "cookies": {"mode": "denylist", "terms": _PRIVATE_KEY_TERMS},
            "url_query_params": {"mode": "denylist", "terms": _PRIVATE_KEY_TERMS},
            "stack_frame_variables": {"mode": "denylist"},
        },
        integrations=[
            FastApiIntegration(failed_request_status_codes={*range(500, 599)}),
            LoggingIntegration(
                breadcrumb_level=logging.INFO,
                event_level=None,
                level=None,
            ),
        ],
    )


# Initialize Sentry for error tracking (production only)
if settings.env == "prod" and settings.sentry_dsn:
    init_astrology_sentry(
        dsn=settings.sentry_dsn,
        environment=f"{settings.env}-astrology",
        release=get_sentry_release("staia-astrology"),
    )


def _create_lifespan(service_settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Initialize and clean up the shared astrology compute runtime."""
        logger.info("Starting %s runtime...", SERVICE_ROLE)
        app.state.service_role = SERVICE_ROLE
        app.state.settings = service_settings
        sentry_sdk.set_tag("service_role", SERVICE_ROLE)
        app.state.astrology_compute_runtime = create_compute_runtime(service_settings)
        try:
            logger.info("%s runtime started successfully", SERVICE_ROLE)
            yield
        finally:
            logger.info("Shutting down %s runtime...", SERVICE_ROLE)
            app.state.astrology_compute_runtime.shutdown()
            logger.info("%s runtime shutdown complete", SERVICE_ROLE)

    return lifespan


def create_app(service_settings: Settings) -> FastAPI:
    """Create the astrology-service FastAPI application."""
    docs_url = None if service_settings.env == "prod" else "/docs"
    redoc_url = None if service_settings.env == "prod" else "/redoc"
    openapi_url = None if service_settings.env == "prod" else "/openapi.json"
    app = FastAPI(
        title=service_settings.app_name,
        version=service_settings.app_version,
        description="Astrology calculation service with hexagonal architecture (Internal Service)",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=_create_lifespan(service_settings),
    )
    app.state.settings = service_settings

    app.add_exception_handler(InvalidBirthDataException, handle_invalid_birth_data)
    app.add_exception_handler(ChartCalculationException, handle_chart_calculation_error)
    app.add_exception_handler(AstrologyServiceException, handle_astrology_service_error)
    app.add_exception_handler(Exception, handle_generic_exception)

    @app.get(
        "/health",
        status_code=status.HTTP_200_OK,
        tags=["Health"],
        summary="Health check",
        description="Check if the service is running",
    )
    async def health_check():
        """Health check endpoint for Railway and monitoring."""
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "healthy",
                "service": service_settings.app_name,
                "version": service_settings.app_version,
                "environment": service_settings.env,
            },
        )

    @app.get(
        "/",
        status_code=status.HTTP_200_OK,
        tags=["Root"],
        summary="API root",
        description="Get API information",
    )
    async def root():
        """Root endpoint with API information."""
        return {
            "service": service_settings.app_name,
            "version": service_settings.app_version,
            "docs": docs_url,
            "health": "/health",
            "api": "/api/v1",
        }

    app.include_router(api_router, prefix="/api")
    return app


app = create_app(settings)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
