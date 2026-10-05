"""FastAPI application factory for the DH-COMPASS browser client."""

from __future__ import annotations

import logging
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from dh_compass import __version__

from .api import (
    area_router,
    calculations_router,
    comparisons_router,
    datasets_router,
    exports_router,
    health_router,
    previews_router,
    projects_router,
    results_router,
    runs_router,
)
from .jobs.calculation import CalculationJobManager
from .jobs.preview import PreviewJobManager, run_preview_worker
from .jobs.run import RunJobManager, run_run_worker
from .persistence.database import create_metadata_engine
from .persistence.migrations import run_migrations
from .schemas import ApiError, FieldError
from .services.geocoding import provider_from_settings
from .services.output_discovery import OutputDiscoveryService
from .services.startup import run_startup_checks
from .settings import WebSettings

LOGGER = logging.getLogger(__name__)
API_PREFIX = "/api/v1"
_REQUEST_ID_PATTERN = re.compile(r"^[\x21-\x7e]{1,128}$")


def _request_id(request: Request) -> str:
    value = request.headers.get("X-Request-ID", "")
    if _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return uuid4().hex


def _request_id_for_error(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) and value else _request_id(request)


def _error_json(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    field_errors: list[FieldError] | None = None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    error = ApiError(
        code=code,
        message=message,
        field_errors=field_errors or [],
        details=details or {},
        request_id=_request_id_for_error(request),
    )
    return JSONResponse(
        status_code=status_code,
        content=error.model_dump(mode="json", exclude_none=True),
        headers={"X-Request-ID": error.request_id},
    )


def _validation_path(location: tuple[Any, ...]) -> str:
    parts = [str(part) for part in location]
    if parts and parts[0] in {"body", "query", "path", "header", "cookie"}:
        # Keep the transport location for non-body values while making body
        # paths directly usable as configuration/form paths.
        if parts[0] == "body":
            parts = parts[1:]
    return ".".join(parts) or "$"


def _validation_errors(exc: RequestValidationError) -> list[FieldError]:
    result: list[FieldError] = []
    for error in exc.errors():
        location = tuple(error.get("loc", ()))
        result.append(
            FieldError(
                path=_validation_path(location),
                message=str(error.get("msg", "Invalid value")),
                code=str(error.get("type")) if error.get("type") else None,
            )
        )
    return result


def _http_error_parts(
    exc: StarletteHTTPException,
) -> tuple[str, str, list[FieldError], dict[str, Any]]:
    default_code = {
        400: "BAD_REQUEST",
        401: "UNAUTHENTICATED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
    }.get(exc.status_code, "HTTP_ERROR")
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code", default_code))
        message = str(detail.get("message", "Request failed."))
        field_errors = [
            FieldError(
                path=str(item["path"]),
                message=str(item["message"]),
                code=str(item["code"]) if item.get("code") is not None else None,
            )
            for item in detail.get("field_errors", [])
            if isinstance(item, dict) and "path" in item and "message" in item
        ]
        details = detail.get("details", {})
        return (
            code,
            message,
            field_errors,
            details if isinstance(details, dict) else {},
        )
    if detail is None:
        return default_code, "Request failed.", [], {}
    return default_code, str(detail), [], {}


class SPAStaticFiles(StaticFiles):
    """Serve compiled assets and fall back to ``index.html`` for client routes."""

    async def get_response(self, path: str, scope: dict[str, Any]):  # type: ignore[override]
        request_path = str(scope.get("path", "")).lstrip("/")
        if (
            path == "api"
            or path.startswith("api/")
            or request_path == "api"
            or request_path.startswith("api/")
        ):
            raise StarletteHTTPException(status_code=404, detail="Not found")
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and scope.get("method") in {"GET", "HEAD"}:
                return await super().get_response("index.html", scope)
            raise


def _street_network_refresher(settings: WebSettings):
    """Create the managed OSM cache refresher used by the local web app."""

    def refresh_street_network(*, scenario: dict[str, Any], dataset: Any, force: bool) -> None:
        # Imports remain inside the explicit refresh boundary: normal API
        # startup must not download data or require the OSM client.
        from dh_compass.preprocessing.street_network import download_street_network
        from dh_compass.web.services.configuration import ConfigurationAdapter

        revision = scenario.get("revision", {})
        document = revision.get("document", {}) if isinstance(revision, dict) else {}
        config = ConfigurationAdapter(settings.project_root).to_app_config(document)
        download_street_network(config, force_refresh=force)

    return refresh_street_network


def _weather_refresher(settings: WebSettings):
    """Acquire validated area-specific weather without user credentials."""

    def refresh_weather(*, scenario: dict[str, Any], dataset: Any, force: bool) -> None:
        from dh_compass.demand.weather import load_weather
        from dh_compass.web.services.configuration import ConfigurationAdapter

        config = ConfigurationAdapter(settings.project_root).to_app_config(
            scenario.get("revision", {}).get("document", {})
        )
        load_weather(config, force_refresh=force)

    return refresh_weather


def _build_lifespan(settings: WebSettings):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_metadata_engine(settings)
        try:
            # Startup is the explicit operational boundary at which migrations
            # are applied. Request handlers never create or alter schema objects.
            migration_version = run_migrations(engine)
            app.state.metadata_engine = engine
            app.state.startup_report = run_startup_checks(
                settings,
                migration_version=migration_version,
            )
            for check in app.state.startup_report.checks:
                if check.status == "warning":
                    LOGGER.warning("startup check %s: %s", check.code, check.message)
                elif check.status == "error":
                    LOGGER.error("startup check %s: %s", check.code, check.message)
            if app.state.startup_report.status == "failed":
                raise RuntimeError("Web startup checks failed")
            app.state.output_discovery = OutputDiscoveryService(settings.output_root)
            if getattr(app.state, "preview_job_manager", None) is None:
                app.state.preview_job_manager = PreviewJobManager(settings)
            if getattr(app.state, "run_job_manager", None) is None:
                app.state.run_job_manager = RunJobManager(settings)
            if getattr(app.state, "calculation_job_manager", None) is None:
                app.state.calculation_job_manager = CalculationJobManager(settings)
            attach_engine = getattr(app.state.run_job_manager, "attach_metadata_engine", None)
            if callable(attach_engine):
                attach_engine(engine)
            app.state.run_job_manager.recover(
                worker_target=getattr(app.state, "run_worker_target", None) or run_run_worker
            )
            if getattr(app.state, "geocoding_provider", None) is None:
                app.state.geocoding_provider = provider_from_settings(settings)
            configured_refreshers = getattr(app.state, "cache_refreshers", {})
            app.state.cache_refreshers = {
                "street_network": _street_network_refresher(settings),
                "weather": _weather_refresher(settings),
                **(configured_refreshers if isinstance(configured_refreshers, dict) else {}),
            }
            recover_calculations = getattr(
                app.state.calculation_job_manager, "recover", None
            )
            if callable(recover_calculations):
                recover_calculations(
                    preview_manager=app.state.preview_job_manager,
                    run_manager=app.state.run_job_manager,
                    refreshers=app.state.cache_refreshers,
                    preview_worker_target=(
                        getattr(app.state, "preview_worker_target", None) or run_preview_worker
                    ),
                    run_worker_target=(
                        getattr(app.state, "run_worker_target", None) or run_run_worker
                    ),
                )
            yield
        finally:
            engine.dispose()

    return lifespan


def create_app(settings: WebSettings | None = None) -> FastAPI:
    """Create a configured FastAPI application.

    The factory is suitable for Uvicorn's ``--factory`` mode and for isolated
    tests with a temporary metadata database and static directory.
    """

    web_settings = settings or WebSettings.from_environment()
    app = FastAPI(
        title="DH-COMPASS API",
        version=__version__,
        description="Browser API for local DH-COMPASS planning workflows.",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=f"{API_PREFIX}/redoc",
        lifespan=_build_lifespan(web_settings),
    )
    app.state.settings = web_settings

    if web_settings.development_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(web_settings.development_cors_origins),
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = _request_id(request)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_json(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            field_errors=_validation_errors(exc),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code, message, field_errors, details = _http_error_parts(exc)
        return _error_json(
            request,
            status_code=exc.status_code,
            code=code,
            message=message,
            field_errors=field_errors,
            details=details,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception("Unhandled web request failure", exc_info=exc)
        return _error_json(
            request,
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred.",
        )

    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(calculations_router, prefix=API_PREFIX)
    app.include_router(projects_router, prefix=API_PREFIX)
    app.include_router(area_router, prefix=API_PREFIX)
    app.include_router(datasets_router, prefix=API_PREFIX)
    app.include_router(previews_router, prefix=API_PREFIX)
    # Durable run routes precede the legacy path-converter result routes so a
    # UUID run is treated as metadata-backed execution state, while existing
    # ``scenario/timestamp`` output IDs continue to use the read-only adapter.
    app.include_router(runs_router, prefix=API_PREFIX)
    app.include_router(comparisons_router, prefix=API_PREFIX)
    app.include_router(exports_router, prefix=API_PREFIX)
    app.include_router(results_router, prefix=API_PREFIX)

    # The service is also available before lifespan startup in tests and in
    # tooling that only inspects the application schema.  It performs no I/O
    # until a request asks it to discover a run.
    app.state.output_discovery = OutputDiscoveryService(web_settings.output_root)
    app.state.startup_report = None
    app.state.preview_job_manager = PreviewJobManager(web_settings)
    app.state.run_job_manager = RunJobManager(web_settings)
    app.state.calculation_job_manager = CalculationJobManager(web_settings)
    app.state.calculation_submission_lock = threading.RLock()
    app.state.preview_worker_target = run_preview_worker
    app.state.run_worker_target = run_run_worker
    app.state.geocoding_provider = provider_from_settings(web_settings)
    app.state.cache_refreshers = {}

    static_path = web_settings.frontend_static_path
    if isinstance(static_path, Path) and static_path.is_dir():
        app.mount(
            "/",
            SPAStaticFiles(directory=str(static_path), html=True),
            name="frontend",
        )

    return app


__all__ = ["API_PREFIX", "SPAStaticFiles", "create_app"]
