"""System health route."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Request

from dh_compass import __version__

from ..schemas import ApiError, HealthResponse, StartupCheckResponse, StartupStatusResponse
from ..services.startup import StartupReport

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={
        400: {"model": ApiError},
        404: {"model": ApiError},
        422: {"model": ApiError},
        500: {"model": ApiError},
    },
    tags=["system"],
    summary="Check API liveness",
)
async def health(request: Request) -> HealthResponse:
    request_id = getattr(request.state, "request_id", None)
    if not isinstance(request_id, str) or not request_id:
        request_id = uuid4().hex
    return HealthResponse(
        status="ok",
        service="dh-compass-api",
        version=__version__,
        request_id=request_id,
    )


def _startup_response(
    report: StartupReport | None,
    *,
    frontend_redesign_enabled: bool = True,
) -> StartupStatusResponse:
    if report is None:
        return StartupStatusResponse(
            status="not_started",
            application_version=__version__,
            api_version=__version__,
            migration_version=None,
            expected_migration_version=0,
            features={"frontend_redesign": frontend_redesign_enabled},
        )
    return StartupStatusResponse(
        status=report.status,
        application_version=report.application_version,
        api_version=report.api_version,
        migration_version=report.migration_version,
        expected_migration_version=report.expected_migration_version,
        frontend_version=report.frontend_version,
        frontend_api_version=report.frontend_api_version,
        features={"frontend_redesign": frontend_redesign_enabled},
        checks=[
            StartupCheckResponse(
                name=check.name,
                status=check.status,
                code=check.code,
                message=check.message,
                details=check.details,
            )
            for check in report.checks
        ],
        checked_at=report.checked_at,
    )


@router.get(
    "/system/status",
    response_model=StartupStatusResponse,
    responses={500: {"model": ApiError}},
    tags=["system"],
    summary="Return startup, data-root, and asset compatibility checks",
)
async def system_status(request: Request) -> StartupStatusResponse:
    return _startup_response(
        getattr(request.app.state, "startup_report", None),
        frontend_redesign_enabled=bool(
            getattr(request.app.state.settings, "frontend_redesign_enabled", True)
        ),
    )


@router.get(
    "/health/ready",
    response_model=StartupStatusResponse,
    responses={500: {"model": ApiError}},
    tags=["system"],
    summary="Return web application readiness checks",
)
async def readiness(request: Request) -> StartupStatusResponse:
    return _startup_response(
        getattr(request.app.state, "startup_report", None),
        frontend_redesign_enabled=bool(
            getattr(request.app.state.settings, "frontend_redesign_enabled", True)
        ),
    )


__all__ = ["health", "readiness", "router", "system_status"]
