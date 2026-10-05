"""Candidate-preview resources and their event stream."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..jobs.preview import PreviewJobManager, PreviewJobProcessError, run_preview_worker
from ..persistence.repositories import (
    ArtifactMetadataRepository,
    DatasetStateRepository,
    JobEventRepository,
    MetadataNotFound,
    PreviewRepository,
)
from ..schemas import (
    ApiError,
    JobEvent,
    PreviewArtifact,
    PreviewCandidate,
    PreviewCandidateResponse,
    PreviewCandidatesResponse,
    PreviewCreate,
    PreviewProgress,
    PreviewResource,
    PreviewSummary,
    ValidationIssue,
)
from ..services.data_readiness import DataReadinessService, DatasetValidationError
from .projects import _adapter, _engine, _not_found, _scenarios

router = APIRouter(tags=["previews"])
_LAYER_FILES = {
    "candidate_areas": "candidate_areas.geojson",
    "lhd": "lhd_edges.geojson",
    "buildings": "buildings.geojson",
    "screened_out": "screened_out.geojson",
}


def _preview_blocking_issues(blocking, refreshers):
    """Weather is acquired by the preview worker, not the request handler."""
    automatic_weather = isinstance(refreshers, Mapping) and callable(refreshers.get("weather"))
    return [
        issue for issue in blocking
        if not (
            automatic_weather and issue.path == "weather"
            and issue.code in {"DATASET_MISSING", "DATASET_SCHEMA_INVALID"}
        )
    ]


def _manager(request: Request) -> PreviewJobManager:
    manager = getattr(request.app.state, "preview_job_manager", None)
    if manager is not None and callable(getattr(manager, "start", None)):
        return manager
    manager = PreviewJobManager(request.app.state.settings)
    request.app.state.preview_job_manager = manager
    return manager


def _previews(request: Request) -> PreviewRepository:
    return PreviewRepository(_engine(request))


def _artifacts(request: Request) -> ArtifactMetadataRepository:
    return ArtifactMetadataRepository(_engine(request))


def _events(request: Request) -> JobEventRepository:
    return JobEventRepository(_engine(request))


def _get_preview(request: Request, preview_id: str) -> dict:
    try:
        return _previews(request).get(preview_id)
    except MetadataNotFound as exc:
        raise _not_found("Preview") from exc


def _public_summary(value: Mapping[str, object] | None) -> PreviewSummary | None:
    if not value:
        return None
    fields = {
        key: value.get(key)
        for key in (
            "candidate_count",
            "included_buildings",
            "included_demand_mwh",
            "network_length_m",
            "excluded_demand_share_pct",
            "screened_out_edge_count",
            "input_revision",
            "threshold_mwh_per_m_a",
            "linear_heat_density_threshold_mwh_per_m_a",
            "candidate_summaries",
            "availability",
        )
        if key in value
    }
    return PreviewSummary(**fields)


def _preview_resource(request: Request, preview: Mapping[str, object]) -> PreviewResource:
    records = _artifacts(request).list_for_preview(str(preview["id"]))
    artifacts: list[PreviewArtifact] = []
    for record in records:
        storage_key = str(record.get("storage_key") or "")
        layer_name = None
        filename = Path(storage_key).name
        for candidate, expected in _LAYER_FILES.items():
            if filename == expected:
                layer_name = candidate
                break
        artifact_status = str(record.get("status", "pending"))
        artifacts.append(
            PreviewArtifact(
                id=str(record["id"]),
                preview_id=str(preview["id"]),
                display_name=str(record["display_name"]),
                description=record.get("description"),
                media_type=str(record["media_type"]),
                byte_size=record.get("byte_size"),
                status=(
                    "available"
                    if artifact_status == "available"
                    else "failed"
                    if artifact_status == "failed"
                    else "pending"
                ),
                checksum_sha256=record.get("checksum_sha256"),
                download_url=(
                    f"/api/v1/previews/{quote(str(preview['id']), safe='')}/artifacts/"
                    f"{quote(str(record['id']), safe='')}/download"
                )
                if artifact_status == "available"
                else None,
                layer_name=layer_name,
                created_at=record["created_at"],
                updated_at=record["updated_at"],
            )
        )
    progress = preview.get("progress")
    warnings = []
    for value in preview.get("warnings") or []:
        if isinstance(value, Mapping):
            warnings.append(ValidationIssue(**dict(value)))
    return PreviewResource(
        id=str(preview["id"]),
        scenario_id=str(preview["scenario_id"]),
        scenario_revision_id=str(preview["scenario_revision_id"]),
        status=str(preview["status"]),  # type: ignore[arg-type]
        stale_reason=preview.get("stale_reason"),
        linear_heat_density_threshold=preview.get("linear_heat_density_threshold"),
        created_at=preview["created_at"],
        updated_at=preview["updated_at"],
        started_at=preview.get("started_at"),
        finished_at=preview.get("finished_at"),
        progress=PreviewProgress(**progress) if isinstance(progress, Mapping) else None,
        summary=_public_summary(preview.get("summary")),
        artifacts=artifacts,
        failure_summary=preview.get("failure_summary"),
        warnings=warnings,
        events_url=f"/api/v1/previews/{quote(str(preview['id']), safe='')}/events",
        candidates_url=f"/api/v1/previews/{quote(str(preview['id']), safe='')}/candidates",
    )


def _candidate(value: Mapping[str, object]) -> PreviewCandidate:
    properties = value.get("properties")
    return PreviewCandidate(
        id=int(value.get("id", -1)),
        decision=str(value["decision"]) if value.get("decision") is not None else None,
        annual_heat_demand_mwh=_number(value.get("annual_heat_demand_mwh")),
        average_linear_heat_density_mwh_per_m_a=_number(
            value.get("average_linear_heat_density_mwh_per_m_a")
        ),
        total_network_length_m=_number(value.get("total_network_length_m")),
        buildings=_integer(value.get("buildings")),
        peak_load_mw=_number(value.get("peak_load_mw")),
        properties=dict(properties) if isinstance(properties, Mapping) else {},
    )


def _number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _integer(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@router.post(
    "/scenarios/{scenario_id}/previews",
    response_model=PreviewResource,
    status_code=202,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}, 422: {"model": ApiError}},
    summary="Queue a candidate-area preprocessing preview",
)
async def create_preview(request: Request, scenario_id: str, payload: PreviewCreate) -> PreviewResource:
    try:
        scenario = _scenarios(request).get(scenario_id)
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc
    current_revision = str(scenario.get("current_revision_id") or "")
    if payload.scenario_revision_id != current_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PREVIEW_REVISION_MISMATCH",
                "message": "The preview must use the scenario's current revision.",
                "details": {
                    "scenario_revision_id": payload.scenario_revision_id,
                    "current_revision_id": current_revision,
                },
            },
        )
    document = scenario["revision"]["document"]
    configured_threshold = document.get("network", {}).get("linear_heat_density_threshold")
    threshold = (
        configured_threshold
        if payload.linear_heat_density_threshold_mwh_per_m_a is None
        else payload.linear_heat_density_threshold_mwh_per_m_a
    )
    if float(threshold) != float(configured_threshold):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PREVIEW_THRESHOLD_NOT_SAVED",
                "message": "Save the LHD threshold as a scenario revision before generating a preview.",
                "field_errors": [
                    {
                        "path": "network.linear_heat_density_threshold",
                        "message": "The requested threshold does not match the selected revision.",
                    }
                ],
            },
        )

    # The API remains the authority for readiness.  This prevents an expensive
    # child process from being created for an obviously missing input.
    try:
        refreshers = getattr(request.app.state, "cache_refreshers", {})
        _, blocking, ready = DataReadinessService(
            _adapter(request),
            DatasetStateRepository(_engine(request)),
            project_root=request.app.state.settings.project_root,
            refreshers=refreshers if isinstance(refreshers, Mapping) else {},
        ).readiness(scenario)
        if not ready:
            blocking = _preview_blocking_issues(blocking, refreshers)
            ready = not blocking
    except DatasetValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "DATASET_VALIDATION_FAILED", "message": str(exc)},
        ) from exc
    if not ready:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DATA_NOT_READY",
                "message": "Required datasets must be ready before a preview can start.",
                "details": {"issues": [issue.model_dump(mode="json") for issue in blocking]},
            },
        )

    preview = _previews(request).create(
        scenario_id,
        current_revision,
        threshold=float(threshold),
        status="queued",
    )
    _events(request).append_ordered(
        preview["id"],
        "preview",
        "job.status_changed",
        {"status": "queued"},
    )
    try:
        _manager(request).start(
            preview_id=preview["id"],
            scenario_id=scenario_id,
            scenario_revision_id=current_revision,
            document=document,
            worker_target=getattr(request.app.state, "preview_worker_target", None) or run_preview_worker,
        )
    except PreviewJobProcessError as exc:
        _previews(request).update_status(preview["id"], "failed", failure_summary=str(exc))
        raise HTTPException(
            status_code=503,
            detail={"code": "PREVIEW_WORKER_UNAVAILABLE", "message": str(exc)},
        ) from exc
    return _preview_resource(request, _previews(request).get(preview["id"]))


@router.get(
    "/previews/{preview_id}",
    response_model=PreviewResource,
    responses={404: {"model": ApiError}},
    summary="Return preview status and summary",
)
async def get_preview(request: Request, preview_id: str) -> PreviewResource:
    return _preview_resource(request, _get_preview(request, preview_id))


@router.post(
    "/previews/{preview_id}/cancel",
    response_model=PreviewResource,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}},
    summary="Request cooperative preview cancellation",
)
async def cancel_preview(request: Request, preview_id: str) -> PreviewResource:
    preview = _get_preview(request, preview_id)
    if preview["status"] in {"ready", "failed", "cancelled", "stale"}:
        return _preview_resource(request, preview)
    if not _manager(request).cancel(preview_id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PREVIEW_PROCESS_NOT_FOUND",
                "message": "The preview worker is no longer attached to this API process.",
            },
        )
    updated = _previews(request).update_status(preview_id, "cancellation_requested")
    _events(request).append_ordered(
        preview_id,
        "preview",
        "job.status_changed",
        {"status": "cancellation_requested"},
    )
    return _preview_resource(request, updated)


@router.get(
    "/previews/{preview_id}/events",
    responses={404: {"model": ApiError}},
    summary="Stream ordered preview progress events",
)
async def preview_events(
    request: Request,
    preview_id: str,
    after_sequence: int = Query(default=0, ge=0),
):
    _get_preview(request, preview_id)
    header_value = request.headers.get("last-event-id")
    if header_value and header_value.isdigit():
        after_sequence = max(after_sequence, int(header_value))
    records = _events(request).list(preview_id, "preview", after_sequence=after_sequence)

    def stream():
        for record in records:
            event = JobEvent(**record)
            yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {event.model_dump_json()}\n\n"
        yield ": heartbeat\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/previews/{preview_id}/candidates",
    response_model=PreviewCandidatesResponse,
    responses={404: {"model": ApiError}},
    summary="Return preview candidate summaries",
)
async def preview_candidates(request: Request, preview_id: str) -> PreviewCandidatesResponse:
    preview = _get_preview(request, preview_id)
    summary = preview.get("summary") or {}
    raw = summary.get("candidate_summaries", []) if isinstance(summary, Mapping) else []
    candidates = [_candidate(value) for value in raw if isinstance(value, Mapping)]
    return PreviewCandidatesResponse(
        preview_id=preview_id,
        available=bool(candidates) or preview["status"] == "ready",
        candidates=candidates,
    )


@router.get(
    "/previews/{preview_id}/candidates/{candidate_id}",
    response_model=PreviewCandidateResponse,
    responses={404: {"model": ApiError}},
    summary="Return one preview candidate summary",
)
async def preview_candidate(
    request: Request, preview_id: str, candidate_id: int
) -> PreviewCandidateResponse:
    preview = _get_preview(request, preview_id)
    summary = preview.get("summary") or {}
    raw = summary.get("candidate_summaries", []) if isinstance(summary, Mapping) else []
    for value in raw:
        if isinstance(value, Mapping) and _integer(value.get("id")) == candidate_id:
            return PreviewCandidateResponse(
                preview_id=preview_id,
                available=True,
                candidate=_candidate(value),
            )
    return PreviewCandidateResponse(
        preview_id=preview_id,
        available=False,
        warnings=[
            ValidationIssue(
                severity="info",
                code="CANDIDATE_NOT_FOUND",
                message=f"Candidate {candidate_id} is not available in this preview.",
            )
        ],
    )


@router.get(
    "/previews/{preview_id}/layers/{layer_name}",
    responses={404: {"model": ApiError}, 409: {"model": ApiError}},
    summary="Return one preview GeoJSON layer",
)
async def preview_layer(request: Request, preview_id: str, layer_name: str):
    preview = _get_preview(request, preview_id)
    filename = _LAYER_FILES.get(layer_name)
    if filename is None:
        raise _not_found("Preview layer")
    artifacts = _artifacts(request).list_for_preview(preview_id)
    record = next((item for item in artifacts if Path(str(item.get("storage_key", ""))).name == filename), None)
    if record is None or record.get("status") != "available":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PREVIEW_LAYER_UNAVAILABLE",
                "message": f"The {layer_name} layer is not available for this preview.",
                "details": {"preview_status": preview["status"]},
            },
        )
    path = _safe_preview_path(request, record.get("storage_key"))
    if path is None or not path.is_file():
        raise _not_found("Preview layer")
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "PREVIEW_LAYER_INVALID", "message": "The preview layer is malformed."},
        ) from exc
    return JSONResponse(content=content)


@router.get(
    "/previews/{preview_id}/artifacts/{artifact_id}/download",
    responses={404: {"model": ApiError}},
    summary="Download one preview artifact",
)
async def download_preview_artifact(request: Request, preview_id: str, artifact_id: str):
    _get_preview(request, preview_id)
    record = next(
        (item for item in _artifacts(request).list_for_preview(preview_id) if item["id"] == artifact_id),
        None,
    )
    if record is None or record.get("status") != "available":
        raise _not_found("Preview artifact")
    path = _safe_preview_path(request, record.get("storage_key"))
    if path is None or not path.is_file():
        raise _not_found("Preview artifact")
    return FileResponse(
        path,
        media_type=str(record["media_type"]),
        filename=path.name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _safe_preview_path(request: Request, storage_key: object) -> Path | None:
    if not isinstance(storage_key, str) or not storage_key:
        return None
    root = Path(request.app.state.settings.output_root).resolve()
    candidate = (root / Path(storage_key)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.is_symlink():
        return None
    return candidate


__all__ = ["router"]
