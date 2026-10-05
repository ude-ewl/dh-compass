"""Contracts shared by the one-command calculation API and its clients.

This module deliberately contains no persistence, network, preprocessing, or
solver work.  It is the small, deterministic boundary that can be approved
before the redesign starts composing the existing project, preview, and run
services.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import cos, isfinite, pi
from typing import Any

# Keep these values explicit and reviewable.  A configuration version is a
# provenance identifier, not a Python package version: changing the defaults
# requires a deliberate contract revision.
DEFAULT_CONFIGURATION_VERSION = "default-v1"
CALCULATION_CONTRACT_VERSION = "1"
BBOX_CRS = "EPSG:4326"
BBOX_COORDINATE_ORDER = ("west", "south", "east", "north")

# This is the supported NRW envelope used for an inexpensive preflight check.
# It is intentionally an envelope rather than a hidden data lookup; the data
# readiness service remains authoritative for exact dataset coverage.
NRW_COVERAGE_BBOX = (5.866, 50.322, 9.531, 52.531)
MIN_BBOX_AREA_KM2 = 0.01
MAX_BBOX_AREA_KM2 = 2_500.0


@dataclass(frozen=True, slots=True)
class BoundingBoxLimits:
    """Server-owned limits for a calculation bounding box."""

    crs: str = BBOX_CRS
    coordinate_order: tuple[str, str, str, str] = BBOX_COORDINATE_ORDER
    coverage_bbox: tuple[float, float, float, float] = NRW_COVERAGE_BBOX
    min_area_km2: float = MIN_BBOX_AREA_KM2
    max_area_km2: float = MAX_BBOX_AREA_KM2


DEFAULT_BBOX_LIMITS = BoundingBoxLimits()


@dataclass(frozen=True, slots=True)
class BoundingBoxIssue:
    """A stable, actionable calculation-input issue."""

    code: str
    message: str
    path: str = "bbox"
    remediation: str | None = None
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": "error",
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "remediation": self.remediation,
            "details": self.details or {},
        }


@dataclass(frozen=True, slots=True)
class BoundingBoxValidation:
    """Deterministic result of validating a calculation bbox."""

    bbox: tuple[float, float, float, float] | None
    area_km2: float | None
    issues: tuple[BoundingBoxIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues and self.bbox is not None


def bbox_area_km2(bbox: Sequence[float]) -> float:
    """Approximate the WGS84 bbox area in square kilometres.

    The result is only used for the coarse maximum-area guard.  Exact
    geospatial coverage and scientific calculations happen downstream.
    """

    west, south, east, north = (float(value) for value in bbox)
    latitude_km = 111.32
    mean_latitude = (south + north) / 2 * pi / 180
    width_km = (east - west) * latitude_km * cos(mean_latitude)
    height_km = (north - south) * latitude_km
    return abs(width_km * height_km)


def validate_calculation_bbox(
    value: Any,
    *,
    limits: BoundingBoxLimits = DEFAULT_BBOX_LIMITS,
) -> BoundingBoxValidation:
    """Validate ``[west, south, east, north]`` for a new calculation.

    The function returns all applicable issues at once so an API can show the
    problem beside the submit action instead of forcing a user through a
    sequence of detached error messages.
    """

    issues: list[BoundingBoxIssue] = []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return BoundingBoxValidation(
            bbox=None,
            area_km2=None,
            issues=(
                BoundingBoxIssue(
                    "BBOX_SHAPE_INVALID",
                    "The bounding box must contain west, south, east, and north coordinates.",
                    remediation="Provide four numeric WGS84 coordinates.",
                ),
            ),
        )
    if len(value) != 4:
        return BoundingBoxValidation(
            bbox=None,
            area_km2=None,
            issues=(
                BoundingBoxIssue(
                    "BBOX_SHAPE_INVALID",
                    "The bounding box must contain exactly four coordinates.",
                    remediation="Use [west, south, east, north].",
                ),
            ),
        )

    try:
        # The transport contract accepts JSON numbers only.  Do not let a
        # numeric string or boolean silently become a coordinate through
        # Python/Pydantic float coercion.
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
            raise ValueError
        values = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        values = ()
    if len(values) != 4 or not all(isfinite(item) for item in values):
        return BoundingBoxValidation(
            bbox=None,
            area_km2=None,
            issues=(
                BoundingBoxIssue(
                    "BBOX_COORDINATES_INVALID",
                    "Bounding-box coordinates must be finite numbers.",
                    remediation="Enter numeric longitude and latitude values.",
                ),
            ),
        )

    west, south, east, north = values
    if (
        not -180 <= west <= 180
        or not -180 <= east <= 180
        or not -90 <= south <= 90
        or not -90 <= north <= 90
    ):
        issues.append(
            BoundingBoxIssue(
                "BBOX_WORLD_BOUNDS",
                "Coordinates must use longitude −180…180 and latitude −90…90.",
                remediation="Check longitude/latitude order and values.",
            )
        )
    if west >= east:
        issues.append(
            BoundingBoxIssue(
                "BBOX_LONGITUDE_ORDER",
                "The west longitude must be smaller than the east longitude.",
                remediation="Swap the horizontal corners or edit the exact extent.",
            )
        )
    if south >= north:
        issues.append(
            BoundingBoxIssue(
                "BBOX_LATITUDE_ORDER",
                "The south latitude must be smaller than the north latitude.",
                remediation="Swap the vertical corners or edit the exact extent.",
            )
        )
    if issues:
        return BoundingBoxValidation(bbox=values, area_km2=None, issues=tuple(issues))

    coverage_west, coverage_south, coverage_east, coverage_north = limits.coverage_bbox
    if (
        west < coverage_west
        or south < coverage_south
        or east > coverage_east
        or north > coverage_north
    ):
        issues.append(
            BoundingBoxIssue(
                "BBOX_OUTSIDE_NRW",
                "The selected area must be inside the supported NRW coverage.",
                remediation="Choose an area within the supported NRW extent.",
                details={"coverage_bbox": list(limits.coverage_bbox)},
            )
        )

    area = bbox_area_km2(values)
    if area < limits.min_area_km2:
        issues.append(
            BoundingBoxIssue(
                "BBOX_TOO_SMALL",
                f"The selected area is smaller than {limits.min_area_km2:g} km².",
                remediation="Draw a slightly larger study area.",
                details={"area_km2": area, "minimum_area_km2": limits.min_area_km2},
            )
        )
    if area > limits.max_area_km2:
        issues.append(
            BoundingBoxIssue(
                "BBOX_TOO_LARGE",
                f"The selected area is larger than {limits.max_area_km2:g} km².",
                remediation="Draw a smaller study area or split the analysis.",
                details={"area_km2": area, "maximum_area_km2": limits.max_area_km2},
            )
        )
    return BoundingBoxValidation(bbox=values, area_km2=area, issues=tuple(issues))


def calculation_contract(
    *,
    limits: BoundingBoxLimits = DEFAULT_BBOX_LIMITS,
) -> dict[str, Any]:
    """Return the JSON-safe contract advertised to a frontend client."""

    return {
        "contract_version": CALCULATION_CONTRACT_VERSION,
        "command": {
            "method": "POST",
            "path": "/api/v1/calculations",
            "body": {"bbox": list(BBOX_COORDINATE_ORDER)},
            "idempotency_header": "Idempotency-Key",
            "idempotency": {
                "same_key_same_bbox": "return_the_original_run",
                "same_key_different_bbox": "409_IDEMPOTENCY_KEY_REUSED",
                "preflight_rejection": "do_not_create_a_run",
                "post_acceptance_failure": "preserve_failed_run_record",
            },
        },
        "bbox": {
            "crs": limits.crs,
            "coordinate_order": list(limits.coordinate_order),
            "coverage_bbox": list(limits.coverage_bbox),
            "min_area_km2": limits.min_area_km2,
            "max_area_km2": limits.max_area_km2,
            "area_calculation": "approximate_wgs84_rectangle",
        },
        "defaults": {
            "configuration_version": DEFAULT_CONFIGURATION_VERSION,
            "source": "configs/default.toml",
            "frontend_may_not_override": True,
        },
        "lifecycle": {
            "statuses": ["queued", "running", "completed", "failed", "cancelled"],
            "terminal_statuses": ["completed", "failed", "cancelled"],
            "response": {
                "run_id": "opaque string",
                "status": "queued",
                "status_url": "/api/v1/runs/{run_id}",
                "bbox": list(BBOX_COORDINATE_ORDER),
                "configuration_version": DEFAULT_CONFIGURATION_VERSION,
            },
        },
    }


__all__ = [
    "BBOX_COORDINATE_ORDER",
    "BBOX_CRS",
    "BoundingBoxIssue",
    "BoundingBoxLimits",
    "BoundingBoxValidation",
    "CALCULATION_CONTRACT_VERSION",
    "DEFAULT_BBOX_LIMITS",
    "DEFAULT_CONFIGURATION_VERSION",
    "MAX_BBOX_AREA_KM2",
    "MIN_BBOX_AREA_KM2",
    "NRW_COVERAGE_BBOX",
    "bbox_area_km2",
    "calculation_contract",
    "validate_calculation_bbox",
]
