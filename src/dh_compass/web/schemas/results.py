"""Schemas for read-only result resources backed by output directories."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .base import APIModel, Page, Pagination

ArtifactAvailabilityStatus = Literal["available", "missing", "invalid"]


class ArtifactAvailability(APIModel):
    """Public metadata for one output file without exposing its server path."""

    id: str
    display_name: str
    kind: str
    media_type: str
    status: ArtifactAvailabilityStatus
    available: bool
    byte_size: int | None = Field(default=None, ge=0)
    checksum_sha256: str | None = None
    error: str | None = None
    download_url: str | None = None


class RunManifest(APIModel):
    """Manifest adapted from a legacy ``outputs/<scenario>/<run>`` folder."""

    id: str
    scenario: str
    timestamp: str
    display_name: str
    status: Literal["completed", "incomplete"]
    source: Literal["legacy_output"]
    legacy: bool = True
    created_at: datetime
    updated_at: datetime
    summary: dict[str, Any] | None = None
    artifacts: list[ArtifactAvailability] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResultProvenance(APIModel):
    """Evidence describing where a browser result section came from.

    Result adapters deliberately expose artifact *identifiers* and checksums,
    never server filesystem paths.  Keeping this metadata beside every result
    section lets clients explain stale/missing data and safely cache immutable
    completed-run responses.
    """

    run_id: str
    adapter: str = "legacy_output"
    source_artifacts: list[str] = Field(default_factory=list)
    artifact_checksums: dict[str, str | None] = Field(default_factory=dict)
    immutable: bool = True


class ResultEnvelope(APIModel):
    """A result section that can explicitly represent missing optional data."""

    available: bool
    data: Any | None = None
    source_artifacts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Section-level availability is intentionally separate from ``data``.  A
    # network response can, for example, contain a final network but no LHD
    # layer.  Older clients may ignore this field safely.
    availability: dict[str, bool] = Field(default_factory=dict)
    provenance: ResultProvenance | None = None
    # SHA-256 of the canonical response excluding this field.  The API also
    # sends the same value as the HTTP ETag.
    content_hash: str | None = None


class ArtifactListResponse(APIModel):
    """Paginated artifact metadata for a completed or legacy run."""

    items: list[ArtifactAvailability]
    pagination: Pagination


RunListResponse = Page[RunManifest]


__all__ = [
    "ArtifactAvailability",
    "ArtifactAvailabilityStatus",
    "ArtifactListResponse",
    "ResultEnvelope",
    "ResultProvenance",
    "RunListResponse",
    "RunManifest",
]
