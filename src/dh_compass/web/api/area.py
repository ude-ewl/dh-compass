"""Study-area and optional geocoding endpoints."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..persistence.repositories import (
    MetadataNotFound,
    PreviewRepository,
    RevisionConflict,
    StudyAreaRepository,
)
from ..schemas import (
    ApiError,
    AreaUpdate,
    BoundaryInspectionResponse,
    GeocodingResult,
    GeocodingSearchRequest,
    GeocodingSearchResponse,
    StudyAreaResponse,
    ValidationIssue,
)
from ..services.geocoding import GeocodingUnavailable
from ..services.study_area import StudyAreaValidationError, bbox_geometry, inspect_boundary
from .projects import _conflict, _engine, _not_found, _scenarios

router = APIRouter(tags=["study-area"])


def _areas(request: Request) -> StudyAreaRepository:
    return StudyAreaRepository(_engine(request))


def _issue_models(values: list[Mapping[str, Any]] | None) -> list[ValidationIssue]:
    return [ValidationIssue(**dict(value)) for value in (values or [])]


def _area_response(request: Request, scenario: Mapping[str, Any]) -> StudyAreaResponse:
    stored = _areas(request).get(str(scenario["id"]))
    document = scenario.get("revision", {}).get("document", {}) if scenario.get("revision") else {}
    scenario_section = document.get("scenario", {}) if isinstance(document, Mapping) else {}
    config_bbox = scenario_section.get("bbox", []) if isinstance(scenario_section, Mapping) else []
    if stored is None:
        bbox = list(config_bbox)
        geometry = bbox_geometry(bbox) if len(bbox) == 4 else None
        return StudyAreaResponse(
            scenario_id=str(scenario["id"]),
            revision_id=str(scenario.get("current_revision_id") or ""),
            execution_bbox=bbox,
            display_geometry=geometry,
            source="bbox",
            validation_issues=[],
            updated_at=scenario["updated_at"],
        )
    return StudyAreaResponse(
        scenario_id=str(scenario["id"]),
        revision_id=str(scenario.get("current_revision_id") or ""),
        execution_bbox=list(stored["execution_bbox"]),
        display_geometry=stored["display_geometry"],
        source=str(stored["source"]),
        imported_filename=stored["imported_filename"],
        crs=stored["crs"],
        validation_issues=_issue_models(stored["validation_issues"]),
        updated_at=stored["updated_at"],
    )


@router.get(
    "/scenarios/{scenario_id}/area",
    response_model=StudyAreaResponse,
    responses={404: {"model": ApiError}},
    summary="Return the display geometry and execution extent for a scenario",
)
async def get_area(request: Request, scenario_id: str) -> StudyAreaResponse:
    try:
        scenario = _scenarios(request).get(scenario_id)
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc
    return _area_response(request, scenario)


@router.put(
    "/scenarios/{scenario_id}/area",
    response_model=StudyAreaResponse,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}, 422: {"model": ApiError}},
    summary="Validate and save a scenario study area",
)
async def update_area(request: Request, scenario_id: str, payload: AreaUpdate) -> StudyAreaResponse:
    scenarios = _scenarios(request)
    try:
        scenario = scenarios.get(scenario_id)
        expected = payload.expected_revision_id or str(scenario["current_revision_id"])
        display_geometry = payload.display_geometry
        issues: list[Mapping[str, Any]] = []
        crs = payload.crs
        if display_geometry is not None:
            inspected = inspect_boundary(display_geometry)
            display_geometry = inspected["display_geometry"]
            issues = list(inspected["issues"])
            crs = crs or inspected.get("normalized_crs")
        elif payload.source == "bbox":
            display_geometry = bbox_geometry(payload.bbox)
            crs = crs or "EPSG:4326"

        current_document = scenario["revision"]["document"]
        scenario_document = current_document.get("scenario", {})
        current_bbox = list(scenario_document.get("bbox", []))
        if current_bbox != payload.bbox:
            updated_document = json.loads(json.dumps(current_document))
            updated_document.setdefault("scenario", {})["bbox"] = list(payload.bbox)
            scenarios.update_config(
                scenario_id,
                expected_revision_id=expected,
                document=updated_document,
            )
            scenario = scenarios.get(scenario_id)
        elif expected != scenario["current_revision_id"]:
            # Even a display-only update must not silently accept a stale editor.
            raise RevisionConflict(
                scenario_id=scenario_id,
                expected_revision_id=expected,
                current_revision_id=scenario["current_revision_id"],
                current_document=scenario["revision"]["document"],
            )

        previous_area = _areas(request).get(scenario_id)
        display_changed = previous_area is not None and (
            previous_area.get("display_geometry") != display_geometry
            or previous_area.get("source") != payload.source
            or previous_area.get("imported_filename") != payload.imported_filename
            or previous_area.get("crs") != crs
        )
        _areas(request).save(
            scenario_id,
            display_geometry=display_geometry,
            execution_bbox=list(payload.bbox),
            source=payload.source,
            imported_filename=payload.imported_filename,
            crs=crs,
            validation_issues=issues,
        )
        if display_changed and scenario.get("preview_id"):
            PreviewRepository(_engine(request)).mark_stale(
                str(scenario["preview_id"]), "Study-area display boundary changed."
            )
        scenario = scenarios.get(scenario_id)
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc
    except RevisionConflict as exc:
        raise _conflict(exc) from exc
    except StudyAreaValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "AREA_VALIDATION_FAILED",
                "message": str(exc),
                "field_errors": exc.issues,
            },
        ) from exc
    return _area_response(request, scenario)


@router.post(
    "/boundaries/inspect",
    response_model=BoundaryInspectionResponse,
    responses={422: {"model": ApiError}},
    summary="Inspect an uploaded GeoJSON boundary",
)
async def inspect_uploaded_boundary(request: Request) -> BoundaryInspectionResponse:
    try:
        content_type = request.headers.get("content-type", "").lower()
        payload: Any
        if "application/json" in content_type:
            payload = await request.json()
            if isinstance(payload, Mapping):
                payload = payload.get("geojson", payload.get("document", payload))
                if isinstance(payload, str):
                    payload = json.loads(payload)
        elif "multipart/form-data" in content_type:
            # ``request.form`` is optional so the API remains usable in a
            # minimal installation without python-multipart.  JSON and raw
            # GeoJSON requests are the documented fallback.
            try:
                form = await request.form()
                upload = form.get("file") or form.get("boundary")
                if upload is None or not hasattr(upload, "read"):
                    raise ValueError("multipart request must contain a file field")
                raw = await upload.read()
                payload = json.loads(raw)
            except AssertionError:
                raw = await request.body()
                payload = _extract_multipart_json(raw, content_type)
        else:
            raw = await request.body()
            payload = json.loads(raw)
        result = inspect_boundary(payload)
    except (StudyAreaValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
        issues = getattr(exc, "issues", None) or [
            {
                "severity": "error",
                "code": "BOUNDARY_INVALID",
                "message": str(exc),
                "remediation": "Upload a valid GeoJSON boundary.",
                "details": {},
            }
        ]
        return BoundaryInspectionResponse(
            valid=False,
            execution_bbox=None,
            display_geometry=None,
            source_crs=None,
            normalized_crs="EPSG:4326",
            issues=[ValidationIssue(**issue) for issue in issues],
            feature_count=0,
        )
    return BoundaryInspectionResponse(**result)


def _extract_multipart_json(raw: bytes, content_type: str) -> Any:
    """Extract a JSON file from a simple multipart upload without a dependency."""

    marker = "boundary="
    if marker not in content_type:
        raise ValueError("multipart request does not declare a boundary")
    boundary = content_type.split(marker, 1)[1].strip().strip('"')
    separator = ("--" + boundary).encode()
    for part in raw.split(separator):
        if b"content-disposition" not in part.lower():
            continue
        head, divider, body = part.partition(b"\r\n\r\n")
        if not divider:
            head, divider, body = part.partition(b"\n\n")
        if not divider:
            continue
        body = body.strip().rstrip(b"-").rstrip()
        if body:
            return json.loads(body)
    raise ValueError("multipart request did not contain a JSON boundary file")


@router.post(
    "/geocoding/search",
    response_model=GeocodingSearchResponse,
    responses={503: {"model": ApiError}},
    summary="Search an optional configured geocoding provider",
)
async def search_geocoding(request: Request, payload: GeocodingSearchRequest) -> GeocodingSearchResponse:
    provider = getattr(request.app.state, "geocoding_provider", None)
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "GEOCODING_UNAVAILABLE",
                "message": "No geocoding provider is configured for this workspace.",
            },
        )
    try:
        values = provider.search(payload.query.strip(), limit=payload.limit)
    except GeocodingUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "GEOCODING_UNAVAILABLE", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "GEOCODING_PROVIDER_FAILED",
                "message": "The configured geocoding provider could not be reached.",
                "details": {"error": str(exc)},
            },
        ) from exc

    results: list[GeocodingResult] = []
    for item in values:
        if not isinstance(item, Mapping):
            continue
        geometry = item.get("geometry")
        bbox = item.get("bbox")
        result_bbox = list(bbox) if isinstance(bbox, (list, tuple)) and len(bbox) == 4 else None
        if result_bbox is None and isinstance(geometry, Mapping):
            try:
                inspected = inspect_boundary(geometry)
                result_bbox = inspected["execution_bbox"]
            except StudyAreaValidationError:
                result_bbox = None
        results.append(
            GeocodingResult(
                display_name=str(item.get("display_name") or payload.query),
                geometry=dict(geometry) if isinstance(geometry, Mapping) else None,
                bbox=result_bbox,
                provider_id=str(item["provider_id"]) if item.get("provider_id") is not None else None,
            )
        )
    return GeocodingSearchResponse(results=results, provider=str(getattr(provider, "name", "custom")))


__all__ = ["router"]
