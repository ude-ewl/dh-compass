"""Transport schemas for comparing immutable completed runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from .base import APIModel


class ComparisonCreate(APIModel):
    """Request a comparison of two to four completed runs."""

    run_ids: list[str] = Field(min_length=2, max_length=4)
    include_unchanged_configuration: bool = False

    @field_validator("run_ids")
    @classmethod
    def unique_run_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("run_ids must not contain empty identifiers")
        if len(set(normalized)) != len(normalized):
            raise ValueError("run_ids must be unique")
        return normalized


CompatibilityStatus = Literal["compatible", "different", "unknown"]


class CompatibilityCheck(APIModel):
    key: Literal["study_area", "data_revision", "model_version", "result_schema"]
    status: CompatibilityStatus
    values: dict[str, Any] = Field(default_factory=dict)
    message: str


class ComparisonResource(APIModel):
    """Normalized comparison data used by both the API and the browser."""

    id: str
    run_ids: list[str]
    created_at: datetime
    updated_at: datetime
    compatibility: list[CompatibilityCheck] = Field(default_factory=list)
    compatible: bool
    baseline_run_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    runs: list[dict[str, Any]] = Field(default_factory=list)
    kpi_differences: list[dict[str, Any]] = Field(default_factory=list)
    # Short aliases keep the response convenient for integrations while the
    # explicit names remain the documented browser contract.
    kpis: list[dict[str, Any]] = Field(default_factory=list)
    configuration_changes: list[dict[str, Any]] = Field(default_factory=list)
    configuration: list[dict[str, Any]] = Field(default_factory=list)
    network: dict[str, Any] = Field(default_factory=dict)
    supply: list[dict[str, Any]] = Field(default_factory=list)
    portfolio: list[dict[str, Any]] = Field(default_factory=list)
    costs: list[dict[str, Any]] = Field(default_factory=list)
    cost_differences: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "CompatibilityCheck",
    "CompatibilityStatus",
    "ComparisonCreate",
    "ComparisonResource",
]
