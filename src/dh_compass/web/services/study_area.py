"""Study-area validation and GeoJSON boundary inspection.

The existing pipeline executes against a WGS84 rectangle.  This module keeps
that execution contract while preserving an optional user-supplied geometry for
map presentation and audit information.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from math import isfinite
from typing import Any

from shapely.geometry import box, mapping, shape
from shapely.ops import transform, unary_union
from shapely.validation import explain_validity


class StudyAreaValidationError(ValueError):
    """Raised when an area cannot be represented by the pipeline."""

    def __init__(self, message: str, *, issues: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.issues = issues or [
            {
                "severity": "error",
                "code": "AREA_INVALID",
                "path": "bbox",
                "message": message,
                "remediation": "Choose a valid WGS84 bounding box or upload a valid boundary.",
                "details": {},
            }
        ]


def validate_bbox(value: Any) -> list[float]:
    """Validate and normalize ``[west, south, east, north]`` WGS84 values."""

    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise StudyAreaValidationError(
            "bbox must contain west, south, east, and north coordinates."
        )
    if len(value) != 4:
        raise StudyAreaValidationError(
            "bbox must contain exactly four coordinates: west, south, east, north."
        )
    try:
        west, south, east, north = (float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise StudyAreaValidationError("bbox coordinates must be numbers.") from exc
    if not all(isfinite(item) for item in (west, south, east, north)):
        raise StudyAreaValidationError("bbox coordinates must be finite numbers.")
    if not -180 <= west <= 180 or not -180 <= east <= 180:
        raise StudyAreaValidationError("bbox longitudes must be between -180 and 180.")
    if not -90 <= south <= 90 or not -90 <= north <= 90:
        raise StudyAreaValidationError("bbox latitudes must be between -90 and 90.")
    if west >= east:
        raise StudyAreaValidationError("bbox must have west < east.")
    if south >= north:
        raise StudyAreaValidationError("bbox must have south < north.")
    return [west, south, east, north]


def _crs_name(document: Mapping[str, Any]) -> str | None:
    raw = document.get("crs")
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    if not isinstance(raw, Mapping):
        return None
    properties = raw.get("properties")
    if isinstance(properties, Mapping):
        for key in ("name", "code", "href"):
            value = properties.get(key)
            if value is not None:
                return str(value)
    return None


def _geometry_items(document: Mapping[str, Any]) -> tuple[list[Any], int]:
    """Extract Shapely-compatible geometries and the source feature count."""

    document_type = document.get("type")
    if document_type == "FeatureCollection":
        raw_features = document.get("features")
        if not isinstance(raw_features, list):
            raise StudyAreaValidationError("GeoJSON FeatureCollection features must be an array.")
        geometries: list[Any] = []
        for feature in raw_features:
            if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
                raise StudyAreaValidationError("Every FeatureCollection item must be a GeoJSON Feature.")
            geometry = feature.get("geometry")
            if geometry is None:
                continue
            if not isinstance(geometry, Mapping):
                raise StudyAreaValidationError("GeoJSON feature geometry must be an object or null.")
            geometries.append(shape(dict(geometry)))
        return geometries, len(raw_features)
    if document_type == "Feature":
        geometry = document.get("geometry")
        if geometry is None or not isinstance(geometry, Mapping):
            raise StudyAreaValidationError("GeoJSON Feature must contain a geometry.")
        return [shape(dict(geometry))], 1
    if document_type in {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    }:
        return [shape(dict(document))], 1
    raise StudyAreaValidationError(
        "Upload a GeoJSON Feature, FeatureCollection, or geometry object."
    )


def _transform_geometry(geometry: Any, source_crs: str | None) -> Any:
    if source_crs is None:
        return geometry
    normalized = source_crs.upper().replace("::", ":").replace("URN:OGC:DEF:CRS:EPSG:", "EPSG:")
    if normalized in {"EPSG:4326", "CRS84", "OGC:CRS84", "WGS84", "WGS 84"}:
        return geometry
    try:
        from pyproj import CRS, Transformer

        source = CRS.from_user_input(source_crs)
        target = CRS.from_epsg(4326)
        transformer = Transformer.from_crs(source, target, always_xy=True)
    except Exception as exc:  # pragma: no cover - depends on optional CRS definitions
        raise StudyAreaValidationError(
            f"The boundary CRS {source_crs!r} could not be transformed to EPSG:4326."
        ) from exc
    return transform(transformer.transform, geometry)


def inspect_boundary(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a GeoJSON document and return normalized display geometry/bbox."""

    if not isinstance(document, Mapping):
        raise StudyAreaValidationError("GeoJSON document must be an object.")
    source_crs = _crs_name(document)
    geometries, feature_count = _geometry_items(document)
    if not geometries:
        raise StudyAreaValidationError("The boundary does not contain any geometries.")

    normalized_geometries = []
    for geometry in geometries:
        if geometry.is_empty:
            continue
        if not geometry.is_valid:
            reason = explain_validity(geometry)
            raise StudyAreaValidationError(
                f"The boundary geometry is invalid: {reason}.",
                issues=[
                    {
                        "severity": "error",
                        "code": "BOUNDARY_GEOMETRY_INVALID",
                        "path": "display_geometry",
                        "message": f"The boundary geometry is invalid: {reason}.",
                        "remediation": "Repair the geometry and upload it again.",
                        "details": {},
                    }
                ],
            )
        normalized_geometries.append(_transform_geometry(geometry, source_crs))

    if not normalized_geometries:
        raise StudyAreaValidationError("The boundary does not contain a non-empty geometry.")
    combined = unary_union(normalized_geometries)
    if combined.is_empty:
        raise StudyAreaValidationError("The boundary does not contain a non-empty geometry.")
    if not combined.is_valid:
        reason = explain_validity(combined)
        raise StudyAreaValidationError(f"The combined boundary is invalid: {reason}.")
    west, south, east, north = combined.bounds
    bbox = validate_bbox([west, south, east, north])
    issues: list[dict[str, Any]] = []
    if source_crs is None:
        issues.append(
            {
                "severity": "warning",
                "code": "BOUNDARY_CRS_ASSUMED",
                "message": "No CRS was declared; coordinates were assumed to be EPSG:4326.",
                "remediation": "Include a CRS declaration when exporting the boundary.",
                "details": {},
            }
        )
    elif str(source_crs).upper() not in {"EPSG:4326", "CRS84", "OGC:CRS84", "WGS84", "WGS 84"}:
        issues.append(
            {
                "severity": "info",
                "code": "BOUNDARY_CRS_TRANSFORMED",
                "message": f"Boundary coordinates were transformed from {source_crs} to EPSG:4326.",
                "remediation": None,
                "details": {"source_crs": source_crs},
            }
        )
    return {
        "valid": True,
        "execution_bbox": bbox,
        "display_geometry": _json_safe(mapping(combined)),
        "source_crs": source_crs,
        "normalized_crs": "EPSG:4326",
        "issues": issues,
        "feature_count": feature_count,
    }


def inspect_boundary_json(content: str | bytes) -> dict[str, Any]:
    """Decode and inspect a boundary upload with a stable error message."""

    try:
        document = json.loads(content)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StudyAreaValidationError("The uploaded file is not valid UTF-8 JSON.") from exc
    return inspect_boundary(document)


def bbox_geometry(bbox: list[float] | tuple[float, float, float, float]) -> dict[str, Any]:
    """Return a GeoJSON polygon for a rectangular execution extent."""

    west, south, east, north = validate_bbox(bbox)
    return _json_safe(mapping(box(west, south, east, north)))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    return value


__all__ = [
    "StudyAreaValidationError",
    "bbox_geometry",
    "inspect_boundary",
    "inspect_boundary_json",
    "validate_bbox",
]
