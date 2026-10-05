"""Health and startup diagnostics schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .base import APIModel


class HealthResponse(APIModel):
    """Minimal liveness response used by the browser and deployment checks."""

    status: Literal["ok"]
    service: str
    version: str
    request_id: str


class StartupCheckResponse(APIModel):
    """A non-sensitive result from one application startup check."""

    name: str
    status: Literal["ok", "warning", "error"]
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class StartupStatusResponse(APIModel):
    """Readiness and compatibility information for a running web process."""

    status: Literal["ready", "degraded", "failed", "not_started"]
    application_version: str
    api_version: str
    migration_version: int | None
    expected_migration_version: int
    frontend_version: str | None = None
    frontend_api_version: str | None = None
    features: dict[str, bool] = Field(default_factory=dict)
    checks: list[StartupCheckResponse] = Field(default_factory=list)
    checked_at: datetime | None = None


__all__ = ["HealthResponse", "StartupCheckResponse", "StartupStatusResponse"]
