"""Transport schemas for dataset readiness and managed cache actions."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .base import APIModel, ValidationIssue

DatasetStatus = Literal[
    "ready",
    "missing",
    "invalid",
    "stale",
    "downloading",
    "unavailable",
]


class DatasetAction(APIModel):
    action: str
    label: str
    allowed: bool = True
    reason: str | None = None


class DatasetDescriptor(APIModel):
    id: str
    label: str
    description: str
    required: bool
    status: DatasetStatus
    path_display: str | None = None
    format: str | None = None
    layer: str | None = None
    columns: list[str] = Field(default_factory=list)
    crs: str | None = None
    extent: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    issues: list[ValidationIssue] = Field(default_factory=list)
    actions: list[DatasetAction] = Field(default_factory=list)
    checked_at: datetime


class DatasetReadinessResponse(APIModel):
    scenario_id: str
    ready: bool
    checked_at: datetime
    datasets: list[DatasetDescriptor] = Field(default_factory=list)
    blocking_issues: list[ValidationIssue] = Field(default_factory=list)


class DatasetValidationRequest(APIModel):
    dataset_ids: list[str] | None = None
    refresh: bool = False


class DatasetValidationResponse(DatasetReadinessResponse):
    pass


class DatasetRefreshRequest(APIModel):
    force: bool = False


class DatasetRefreshResponse(APIModel):
    scenario_id: str
    dataset: DatasetDescriptor
    action: str
    message: str


class DatasetLayerResponse(APIModel):
    dataset_id: str
    source: str | None = None
    truncated: bool = False
    geojson: dict[str, Any]


__all__ = [
    "DatasetAction",
    "DatasetDescriptor",
    "DatasetLayerResponse",
    "DatasetRefreshRequest",
    "DatasetRefreshResponse",
    "DatasetReadinessResponse",
    "DatasetStatus",
    "DatasetValidationRequest",
    "DatasetValidationResponse",
]
