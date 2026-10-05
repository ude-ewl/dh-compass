"""Stable transport schemas shared by web API resources."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from ..persistence.identifiers import new_identifier, utc_now


class APIModel(BaseModel):
    """Base model with strict object keys for a predictable API contract."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class FieldError(APIModel):
    """A validation error associated with an input/configuration path."""

    path: str
    message: str
    code: str | None = None


class ApiError(APIModel):
    """Normalized error envelope returned by every API failure."""

    code: str
    message: str
    field_errors: list[FieldError] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


# The longer name is useful to callers that prefer an explicit response name.
ErrorResponse = ApiError


class ValidationIssue(APIModel):
    """Actionable validation information for data and scenario screens."""

    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    path: str | None = None
    remediation: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class PersistedIdentity(APIModel):
    """Identifiers and timestamps common to persisted resources."""

    id: str = Field(default_factory=new_identifier)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class JobProgress(APIModel):
    """Optional determinate progress attached to a preview or run."""

    stage: str | None = None
    completed: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    fraction: float | None = Field(default=None, ge=0, le=1)


JobStatus = Literal[
    "queued",
    "running",
    "cancellation_requested",
    "cancelled",
    "completed",
    "failed",
]


class Job(PersistedIdentity):
    """Base job representation used by preview and run APIs."""

    kind: str
    status: JobStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: JobProgress | None = None
    failure_summary: str | None = None


ArtifactStatus = Literal["pending", "available", "failed"]


class Artifact(PersistedIdentity):
    """Metadata for a generated or downloadable output artifact."""

    display_name: str
    description: str | None = None
    media_type: str
    byte_size: int | None = Field(default=None, ge=0)
    status: ArtifactStatus
    checksum_sha256: str | None = None
    download_url: str | None = None


class Pagination(APIModel):
    """Page metadata shared by collection endpoints."""

    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    total: int = Field(ge=0)
    has_next: bool
    has_previous: bool


ItemT = TypeVar("ItemT")


class Page(APIModel, Generic[ItemT]):
    """Generic paginated collection envelope."""

    items: list[ItemT]
    pagination: Pagination


__all__ = [
    "APIModel",
    "ApiError",
    "Artifact",
    "ArtifactStatus",
    "ErrorResponse",
    "FieldError",
    "Job",
    "JobProgress",
    "JobStatus",
    "Page",
    "Pagination",
    "PersistedIdentity",
    "ValidationIssue",
]
