"""Transport schemas for immutable optimization runs and their progress."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from .base import APIModel, Artifact, Page, Pagination, ValidationIssue

RunStatus = Literal[
    "queued",
    "running",
    "cancellation_requested",
    "cancelled",
    "completed",
    "failed",
]


class RunProgress(APIModel):
    stage: str | None = None
    completed: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    fraction: float | None = Field(default=None, ge=0, le=1)


class CandidateProgress(APIModel):
    completed_candidates: int = Field(default=0, ge=0)
    total_candidates: int | None = Field(default=None, ge=0)
    connected_candidates: int = Field(default=0, ge=0)
    rejected_candidates: int = Field(default=0, ge=0)
    current_candidate_id: int | None = None
    current_candidate_index: int | None = Field(default=None, ge=0)
    decision: str | None = None


class RunCreate(APIModel):
    scenario_revision_id: str
    preview_id: str
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    output_label: str | None = Field(default=None, max_length=120)
    warning_acknowledgements: list[str] = Field(default_factory=list)
    # Accepting the key in the body is useful for non-browser integrations;
    # browser clients normally use the Idempotency-Key header.
    idempotency_key: str | None = Field(default=None, max_length=200)

    @field_validator("name", "description", "output_label", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value


class RunResource(APIModel):
    id: str
    scenario_id: str
    scenario_revision_id: str
    preview_id: str | None = None
    name: str
    description: str | None = None
    output_label: str | None = None
    status: RunStatus
    stage: str | None = None
    progress: RunProgress | None = None
    candidate_progress: CandidateProgress | None = None
    configuration_snapshot: dict[str, Any] = Field(default_factory=dict)
    configuration_version: str | None = None
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    data_snapshot: dict[str, Any] = Field(default_factory=dict)
    application_version: str | None = None
    solver_name: str | None = None
    solver_version: str | None = None
    process_identity: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    warnings: list[ValidationIssue] = Field(default_factory=list)
    failure_summary: str | None = None
    failure_details: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[Artifact] = Field(default_factory=list)
    log_url: str | None = None
    events_url: str | None = None
    cancel_url: str | None = None
    results_url: str | None = None
    manifest_url: str | None = None


class RunEvent(APIModel):
    id: str
    run_id: str
    job_kind: Literal["run"] = "run"
    sequence: int = Field(ge=1)
    event_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class RunArtifactListResponse(APIModel):
    items: list[Artifact]
    pagination: Pagination


class RunLogResponse(APIModel):
    run_id: str
    available: bool
    content: str = ""
    truncated: bool = False


class RunSummary(APIModel):
    """Lightweight run reference for the recovery list.

    The recovery list only has to answer "which calculation was this and can I
    reopen it?".  Configuration snapshots, data versions, and artifacts stay in
    the authoritative run resource, so this payload stays small even for a long
    history.
    """

    id: str
    name: str
    status: RunStatus
    stage: str | None = None
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RunSummaryListResponse(Page[RunSummary]):
    """Paginated recent-run page for `/recent`."""


__all__ = [
    "CandidateProgress",
    "RunArtifactListResponse",
    "RunCreate",
    "RunEvent",
    "RunLogResponse",
    "RunProgress",
    "RunResource",
    "RunStatus",
    "RunSummary",
    "RunSummaryListResponse",
]
