"""Transport schemas for durable report and bundle exports."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from .base import APIModel

ExportKind = Literal["report", "bundle", "csv"]
ExportStatus = Literal["queued", "running", "available", "failed"]


class ExportCreate(APIModel):
    """Optional export hints; generation remains server-authoritative."""

    table: str | None = None


class RetentionCleanupResponse(APIModel):
    older_than_days: int
    dry_run: bool
    candidates: int
    removed: int
    run_artifacts_preserved: bool


class ExportJobResource(APIModel):
    id: str
    run_id: str
    kind: ExportKind
    status: ExportStatus
    display_name: str
    media_type: str
    byte_size: int | None = None
    checksum_sha256: str | None = None
    download_url: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


__all__ = [
    "ExportCreate",
    "ExportJobResource",
    "ExportKind",
    "ExportStatus",
    "RetentionCleanupResponse",
]
