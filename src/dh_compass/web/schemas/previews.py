"""Transport schemas for asynchronous candidate previews."""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any, Literal

from pydantic import AliasChoices, Field, field_validator

from .base import APIModel, Artifact, ValidationIssue

PreviewStatus = Literal[
    "queued",
    "running",
    "cancellation_requested",
    "ready",
    "stale",
    "failed",
    "cancelled",
]


class PreviewProgress(APIModel):
    stage: str | None = None
    completed: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    fraction: float | None = Field(default=None, ge=0, le=1)


class PreviewSummary(APIModel):
    candidate_count: int = Field(default=0, ge=0)
    included_buildings: int | None = Field(default=None, ge=0)
    included_demand_mwh: float | None = None
    network_length_m: float | None = Field(default=None, ge=0)
    excluded_demand_share_pct: float | None = None
    screened_out_edge_count: int | None = Field(default=None, ge=0)
    input_revision: str | None = None
    threshold_mwh_per_m_a: float | None = None
    linear_heat_density_threshold_mwh_per_m_a: float | None = None
    candidate_summaries: list[dict[str, Any]] = Field(default_factory=list)
    availability: dict[str, bool] = Field(default_factory=dict)


class PreviewCreate(APIModel):
    scenario_revision_id: str
    linear_heat_density_threshold_mwh_per_m_a: float | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices(
            "linear_heat_density_threshold_mwh_per_m_a",
            "linear_heat_density_threshold",
            "threshold",
        ),
    )

    @field_validator("linear_heat_density_threshold_mwh_per_m_a")
    @classmethod
    def finite_threshold(cls, value: float | None) -> float | None:
        if value is not None and not isfinite(value):
            raise ValueError("linear heat density threshold must be finite")
        return value


class PreviewArtifact(Artifact):
    preview_id: str
    layer_name: str | None = None


class PreviewResource(APIModel):
    id: str
    scenario_id: str
    scenario_revision_id: str
    status: PreviewStatus
    stale_reason: str | None = None
    linear_heat_density_threshold: float | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: PreviewProgress | None = None
    summary: PreviewSummary | None = None
    artifacts: list[PreviewArtifact] = Field(default_factory=list)
    failure_summary: str | None = None
    warnings: list[ValidationIssue] = Field(default_factory=list)
    events_url: str | None = None
    candidates_url: str | None = None


class PreviewCandidate(APIModel):
    id: int
    decision: str | None = None
    annual_heat_demand_mwh: float | None = None
    average_linear_heat_density_mwh_per_m_a: float | None = None
    total_network_length_m: float | None = None
    buildings: int | None = None
    peak_load_mw: float | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class PreviewCandidatesResponse(APIModel):
    preview_id: str
    available: bool
    candidates: list[PreviewCandidate] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)


class PreviewCandidateResponse(APIModel):
    preview_id: str
    candidate: PreviewCandidate | None = None
    available: bool
    warnings: list[ValidationIssue] = Field(default_factory=list)


class JobEvent(APIModel):
    id: str
    job_id: str
    job_kind: Literal["preview", "run"]
    sequence: int = Field(ge=1)
    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


__all__ = [
    "JobEvent",
    "PreviewArtifact",
    "PreviewCandidate",
    "PreviewCandidateResponse",
    "PreviewCandidatesResponse",
    "PreviewCreate",
    "PreviewProgress",
    "PreviewResource",
    "PreviewStatus",
    "PreviewSummary",
]
