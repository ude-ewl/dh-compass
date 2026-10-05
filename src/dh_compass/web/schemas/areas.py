"""Transport schemas for study-area selection and boundary inspection."""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any

from pydantic import AliasChoices, Field, field_validator

from .base import APIModel, ValidationIssue


class AreaUpdate(APIModel):
    """Update a scenario's display area and execution bounding box.

    The display geometry is deliberately separate from ``bbox``.  A polygon
    uploaded by a user is useful context, while preprocessing continues to use
    the rectangular execution extent understood by the existing pipeline.
    """

    bbox: list[float] = Field(
        min_length=4,
        max_length=4,
        validation_alias=AliasChoices("bbox", "execution_bbox", "coordinates"),
    )
    expected_revision_id: str | None = None
    display_geometry: dict[str, Any] | None = None
    source: str = Field(default="bbox", min_length=1, max_length=80)
    imported_filename: str | None = Field(default=None, max_length=255)
    crs: str | None = Field(default=None, max_length=120)

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        if len(value) != 4 or not all(
            isinstance(item, (int, float)) and not isinstance(item, bool) for item in value
        ):
            raise ValueError("bbox must contain west, south, east, and north")
        west, south, east, north = (float(item) for item in value)
        if not all(isfinite(item) for item in (west, south, east, north)):
            raise ValueError("bbox coordinates must be finite")
        if not -180 <= west <= 180 or not -180 <= east <= 180:
            raise ValueError("bbox longitude must be between -180 and 180")
        if not -90 <= south <= 90 or not -90 <= north <= 90:
            raise ValueError("bbox latitude must be between -90 and 90")
        if west >= east or south >= north:
            raise ValueError("bbox must have west < east and south < north")
        return [west, south, east, north]


class StudyAreaResponse(APIModel):
    scenario_id: str
    revision_id: str
    execution_bbox: list[float]
    display_geometry: dict[str, Any] | None = None
    source: str
    imported_filename: str | None = None
    crs: str | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    updated_at: datetime


class BoundaryInspectionResponse(APIModel):
    valid: bool
    execution_bbox: list[float] | None = None
    display_geometry: dict[str, Any] | None = None
    source_crs: str | None = None
    normalized_crs: str = "EPSG:4326"
    issues: list[ValidationIssue] = Field(default_factory=list)
    feature_count: int = Field(default=0, ge=0)


class GeocodingSearchRequest(APIModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


class GeocodingResult(APIModel):
    display_name: str
    geometry: dict[str, Any] | None = None
    bbox: list[float] | None = None
    provider_id: str | None = None


class GeocodingSearchResponse(APIModel):
    results: list[GeocodingResult] = Field(default_factory=list)
    provider: str
    warning: str | None = None


__all__ = [
    "AreaUpdate",
    "BoundaryInspectionResponse",
    "GeocodingResult",
    "GeocodingSearchRequest",
    "GeocodingSearchResponse",
    "StudyAreaResponse",
]
