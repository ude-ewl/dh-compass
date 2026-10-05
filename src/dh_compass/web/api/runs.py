"""Asynchronous optimization run resources and progress streams."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from dh_compass import __version__

from ..jobs.run import RunJobManager, RunJobProcessError, run_run_worker
from ..persistence.repositories import (
    ArtifactMetadataRepository,
    AuditRepository,
    JobEventRepository,
    MetadataNotFound,
    PreviewRepository,
    RunRepository,
)
from ..schemas import (
    ApiError,
    Artifact,
    CandidateProgress,
    Pagination,
    RunArtifactListResponse,
    RunCreate,
    RunEvent,
    RunLogResponse,
    RunProgress,
    RunResource,
    RunSummary,
    RunSummaryListResponse,
    ValidationIssue,
)
from .projects import _engine, _not_found, _scenarios

router = APIRouter(tags=["runs"])
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_TERMINAL = {"completed", "failed", "cancelled"}


def _manager(request: Request) -> RunJobManager:
    manager = getattr(request.app.state, "run_job_manager", None)
    if manager is not None and callable(getattr(manager, "start", None)):
        attach_engine = getattr(manager, "attach_metadata_engine", None)
        metadata_engine = getattr(request.app.state, "metadata_engine", None)
        if callable(attach_engine) and metadata_engine is not None:
            attach_engine(metadata_engine)
        return manager
    manager = RunJobManager(request.app.state.settings)
    request.app.state.run_job_manager = manager
    return manager


def _runs(request: Request) -> RunRepository:
    return RunRepository(_engine(request))


def _previews(request: Request) -> PreviewRepository:
    return PreviewRepository(_engine(request))


def _events(request: Request) -> JobEventRepository:
    return JobEventRepository(_engine(request))


def _artifacts(request: Request) -> ArtifactMetadataRepository:
    return ArtifactMetadataRepository(_engine(request))


def _get_run(request: Request, run_id: str) -> dict:
    try:
        return _runs(request).get(run_id)
    except MetadataNotFound as exc:
        raise _not_found("Run") from exc


def _append_event(request: Request, run_id: str, event_type: str, data: Mapping[str, object]) -> None:
    _events(request).append_ordered(run_id, "run", event_type, data)


def _artifact(record: Mapping[str, object], request: Request, run_id: str) -> Artifact:
    status = str(record.get("status") or "pending")
    return Artifact(
        id=str(record["id"]),
        display_name=str(record["display_name"]),
        description=record.get("description"),
        media_type=str(record["media_type"]),
        byte_size=record.get("byte_size"),
        status=status if status in {"pending", "available", "failed"} else "pending",
        checksum_sha256=record.get("checksum_sha256"),
        download_url=(
            f"/api/v1/runs/{quote(run_id, safe='')}/artifacts/"
            f"{quote(str(record['id']), safe='')}/download"
        )
        if status == "available"
        else None,
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


def _warnings(value: object) -> list[ValidationIssue]:
    result: list[ValidationIssue] = []
    if not isinstance(value, list):
        return result
    for item in value:
        if isinstance(item, Mapping):
            try:
                result.append(ValidationIssue(**dict(item)))
            except Exception:
                result.append(
                    ValidationIssue(
                        severity="warning",
                        code="WORKER_WARNING",
                        message=str(item.get("message", item)),
                        details=dict(item),
                    )
                )
        else:
            result.append(
                ValidationIssue(
                    severity="warning",
                    code="WORKER_WARNING",
                    message=str(item),
                )
            )
    return result


def _run_resource(request: Request, run: Mapping[str, object]) -> RunResource:
    run_id = str(run["id"])
    artifact_records = _artifacts(request).list_for_run(run_id)
    manifest_record = next(
        (
            record
            for record in artifact_records
            if Path(str(record.get("storage_key") or "")).name == "run_manifest.json"
        ),
        None,
    )
    progress = run.get("progress")
    candidate_progress = run.get("candidate_progress")
    solver = run.get("solver") if isinstance(run.get("solver"), Mapping) else {}
    process_identity = run.get("process_identity")
    return RunResource(
        id=run_id,
        scenario_id=str(run["scenario_id"]),
        scenario_revision_id=str(run["scenario_revision_id"]),
        preview_id=run.get("preview_id"),
        name=str(run["name"]),
        description=run.get("description"),
        output_label=run.get("output_label"),
        status=str(run["status"]),  # type: ignore[arg-type]
        stage=run.get("stage"),
        progress=RunProgress(**progress) if isinstance(progress, Mapping) else None,
        candidate_progress=(
            CandidateProgress(**candidate_progress)
            if isinstance(candidate_progress, Mapping)
            else None
        ),
        configuration_snapshot=(
            dict(run.get("configuration_snapshot") or {})
            if isinstance(run.get("configuration_snapshot"), Mapping)
            else {}
        ),
        configuration_version=run.get("configuration_version"),
        bbox=(
            list(run.get("bbox"))
            if isinstance(run.get("bbox"), (list, tuple))
            else None
        ),
        data_snapshot=(
            dict(run.get("data_snapshot") or {})
            if isinstance(run.get("data_snapshot"), Mapping)
            else {}
        ),
        application_version=run.get("application_version"),
        solver_name=solver.get("name"),
        solver_version=solver.get("version"),
        process_identity=dict(process_identity) if isinstance(process_identity, Mapping) else None,
        started_at=run.get("started_at"),
        finished_at=run.get("finished_at"),
        created_at=run["created_at"],
        updated_at=run["updated_at"],
        warnings=_warnings(run.get("warnings")),
        failure_summary=run.get("failure_summary"),
        failure_details=(
            dict(run.get("failure_details") or {})
            if isinstance(run.get("failure_details"), Mapping)
            else {}
        ),
        artifacts=[_artifact(record, request, run_id) for record in artifact_records],
        log_url=f"/api/v1/runs/{quote(run_id, safe='')}/logs"
        if run.get("log_storage_key")
        else None,
        events_url=f"/api/v1/runs/{quote(run_id, safe='')}/events",
        cancel_url=(
            f"/api/v1/runs/{quote(run_id, safe='')}/cancel"
            if str(run["status"]) not in _TERMINAL
            else None
        ),
        results_url=(
            f"/runs/{quote(str(run['output_storage_key']), safe='')}/results/overview"
            if str(run["status"]) == "completed" and run.get("output_storage_key")
            else None
        ),
        manifest_url=(
            f"/api/v1/runs/{quote(run_id, safe='')}/artifacts/"
            f"{quote(str(manifest_record['id']), safe='')}/download"
            if manifest_record is not None and manifest_record.get("status") == "available"
            else None
        ),
    )


@router.post(
    "/scenarios/{scenario_id}/runs",
    response_model=RunResource,
    status_code=202,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}, 422: {"model": ApiError}},
    summary="Queue an immutable optimization run",
)
async def create_run(
    request: Request,
    scenario_id: str,
    payload: RunCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RunResource:
    try:
        scenario = _scenarios(request).get(scenario_id)
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc

    key = (idempotency_key or payload.idempotency_key or "").strip() or None
    if key:
        existing = _runs(request).find_by_idempotency(scenario_id, key)
        if existing is not None:
            if (
                existing["scenario_revision_id"] != payload.scenario_revision_id
                or existing.get("preview_id") != payload.preview_id
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "IDEMPOTENCY_KEY_REUSED",
                        "message": "The idempotency key belongs to a different run request.",
                    },
                )
            return _run_resource(request, existing)

    current_revision = str(scenario.get("current_revision_id") or "")
    if payload.scenario_revision_id != current_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_REVISION_MISMATCH",
                "message": "The run must use the scenario's current revision.",
                "details": {
                    "scenario_revision_id": payload.scenario_revision_id,
                    "current_revision_id": current_revision,
                },
            },
        )

    try:
        preview = _previews(request).get(payload.preview_id)
    except MetadataNotFound as exc:
        raise _not_found("Preview") from exc
    if (
        preview["scenario_id"] != scenario_id
        or preview["scenario_revision_id"] != payload.scenario_revision_id
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_PREVIEW_MISMATCH",
                "message": "The candidate preview belongs to another scenario revision.",
            },
        )
    if scenario.get("preview_id") != payload.preview_id or preview["status"] != "ready":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_PREVIEW_NOT_READY",
                "message": "A current, ready candidate preview is required before starting a run.",
                "details": {
                    "preview_status": preview["status"],
                    "preview_id": scenario.get("preview_id"),
                },
            },
        )
    preview_warnings = preview.get("warnings") or []
    warning_codes = {
        str(item.get("code"))
        for item in preview_warnings
        if isinstance(item, Mapping) and item.get("severity") in {"warning", "error"}
    }
    acknowledged = set(payload.warning_acknowledgements)
    missing_warnings = sorted(code for code in warning_codes if code not in acknowledged)
    if missing_warnings:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_WARNINGS_NOT_ACKNOWLEDGED",
                "message": "Review and acknowledge the warnings before starting this run.",
                "details": {"warning_codes": missing_warnings},
            },
        )
    if payload.output_label is not None and not _SAFE_LABEL.fullmatch(payload.output_label):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_OUTPUT_LABEL",
                "message": "Output labels may contain only letters, numbers, dots, underscores, and hyphens.",
                "field_errors": [
                    {
                        "path": "output_label",
                        "message": "Use a safe filename label without path separators.",
                    }
                ],
            },
        )

    name = payload.name or f"{scenario['name']} run"
    try:
        run = _runs(request).create(
            scenario_id,
            payload.scenario_revision_id,
            name,
            description=payload.description,
            preview_id=payload.preview_id,
            configuration_snapshot=scenario["revision"]["document"],
            idempotency_key=key,
            application_version=__version__,
            output_label=payload.output_label,
        )
    except Exception as exc:
        # A concurrent request can win the unique idempotency index between
        # the lookup above and INSERT.  Return the winning immutable resource.
        if key:
            existing = _runs(request).find_by_idempotency(scenario_id, key)
            if existing is not None:
                if (
                    existing["scenario_revision_id"] != payload.scenario_revision_id
                    or existing.get("preview_id") != payload.preview_id
                ):
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "IDEMPOTENCY_KEY_REUSED",
                            "message": "The idempotency key belongs to a different run request.",
                        },
                    )
                return _run_resource(request, existing)
        raise HTTPException(
            status_code=500,
            detail={"code": "RUN_CREATE_FAILED", "message": "The run could not be created."},
        ) from exc

    _append_event(request, run["id"], "job.status_changed", {"status": "queued"})
    _audit(request, "run.created", "run", run["id"], {"scenario_id": scenario_id})
    try:
        _manager(request).start(
            run_id=run["id"],
            scenario_id=scenario_id,
            scenario_revision_id=payload.scenario_revision_id,
            preview_id=payload.preview_id,
            configuration_snapshot=scenario["revision"]["document"],
            output_label=payload.output_label,
            worker_target=getattr(request.app.state, "run_worker_target", None) or run_run_worker,
        )
    except RunJobProcessError as exc:
        run = _runs(request).update_status(
            run["id"],
            "failed",
            stage="failed",
            failure_summary=str(exc),
            failure_details={"code": "RUN_WORKER_UNAVAILABLE"},
        )
        _append_event(request, run["id"], "job.failed", {"message": str(exc)})
    return _run_resource(request, _runs(request).get(run["id"]))


def _run_summary(run: Mapping[str, object]) -> RunSummary:
    """Reduce a durable run record to its recovery-list fields."""

    bbox = run.get("bbox")
    return RunSummary(
        id=str(run["id"]),
        name=str(run["name"]),
        status=str(run["status"]),  # type: ignore[arg-type]
        stage=run.get("stage"),
        bbox=list(bbox) if isinstance(bbox, (list, tuple)) else None,
        started_at=run.get("started_at"),
        finished_at=run.get("finished_at"),
        created_at=run["created_at"],  # type: ignore[arg-type]
        updated_at=run["updated_at"],  # type: ignore[arg-type]
    )


@router.get(
    "/runs/recent",
    response_model=RunSummaryListResponse,
    responses={404: {"model": ApiError}},
    summary="List recent calculation runs for recovery",
)
async def list_recent_runs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> RunSummaryListResponse:
    """Return metadata-backed runs so a run link can always be recovered.

    Declared before ``/runs/{run_id}`` so the literal path is matched here
    instead of being read as a run identifier.  Only durable run records are
    returned: the read-only legacy output discovery keeps its own portal.
    """

    repository = _runs(request)
    total = repository.count()
    start = (page - 1) * page_size
    items = [
        _run_summary(record)
        for record in repository.list_recent(limit=page_size, offset=start)
    ]
    return RunSummaryListResponse(
        items=items,
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total=total,
            has_next=start + page_size < total,
            has_previous=page > 1 and start < total,
        ),
    )


@router.get(
    "/runs/{run_id}",
    response_model=RunResource,
    responses={404: {"model": ApiError}},
    summary="Return authoritative optimization run state",
)
async def get_run(request: Request, run_id: str) -> RunResource:
    return _run_resource(request, _get_run(request, run_id))


@router.post(
    "/runs/{run_id}/cancel",
    response_model=RunResource,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}},
    summary="Request cooperative run cancellation",
)
async def cancel_run(request: Request, run_id: str) -> RunResource:
    run = _get_run(request, run_id)
    if str(run["status"]) in _TERMINAL:
        return _run_resource(request, run)
    if not _manager(request).cancel(run_id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_PROCESS_NOT_FOUND",
                "message": "The run worker is no longer attached to this API process.",
            },
        )
    _audit(request, "run.cancel_requested", "run", run_id, {})
    return _run_resource(request, _runs(request).get(run_id))


@router.get(
    "/runs/{run_id}/events",
    responses={404: {"model": ApiError}},
    summary="Stream ordered optimization progress events",
)
async def run_events(
    request: Request,
    run_id: str,
    after_sequence: int = Query(default=0, ge=0),
    format: str = Query(default="sse", pattern="^(sse|json)$"),
):
    _get_run(request, run_id)
    header_value = request.headers.get("last-event-id")
    if header_value and header_value.isdigit():
        after_sequence = max(after_sequence, int(header_value))
    records = _events(request).list(run_id, "run", after_sequence=after_sequence)
    event_models = [_run_event(run_id, record) for record in records]
    if format == "json":
        return JSONResponse(content=[event.model_dump(mode="json") for event in event_models])

    async def stream():
        """Keep the connection open and poll durable events for new records.

        SQLite is the authoritative cross-process event store, so polling it in
        the SSE producer avoids an in-memory pub/sub dependency that would lose
        events after an API restart. Sequence IDs make replay idempotent.
        """

        last_sequence = after_sequence
        next_heartbeat = 0.0
        while True:
            records = _events(request).list(run_id, "run", after_sequence=last_sequence)
            for record in records:
                event = _run_event(run_id, record)
                last_sequence = event.sequence
                yield (
                    f"id: {event.sequence}\nevent: {event.event_type}"
                    f"\ndata: {event.model_dump_json()}\n\n"
                )

            current = _get_run(request, run_id)
            if str(current["status"]) in _TERMINAL:
                return

            now = time.monotonic()
            if now >= next_heartbeat:
                heartbeat = RunEvent(
                    id=f"heartbeat-{run_id}-{last_sequence}",
                    run_id=run_id,
                    sequence=max(1, last_sequence),
                    event_type="heartbeat",
                    data={"status": "connected", "last_sequence": last_sequence},
                    occurred_at=datetime.now(timezone.utc),
                )
                yield f"event: heartbeat\ndata: {heartbeat.model_dump_json()}\n\n"
                next_heartbeat = now + 15.0
            await asyncio.sleep(0.25)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/runs/{run_id}/logs",
    response_model=RunLogResponse,
    responses={404: {"model": ApiError}},
    summary="Return persisted run diagnostics",
)
async def run_logs(
    request: Request,
    run_id: str,
    max_bytes: int = Query(default=500_000, ge=1_000, le=5_000_000),
) -> RunLogResponse:
    run = _get_run(request, run_id)
    path = _safe_storage_path(request, run.get("log_storage_key"))
    if path is None or not path.is_file():
        return RunLogResponse(run_id=run_id, available=False)
    content = path.read_bytes()
    truncated = len(content) > max_bytes
    if truncated:
        content = content[-max_bytes:]
    return RunLogResponse(
        run_id=run_id,
        available=True,
        content=content.decode("utf-8", errors="replace"),
        truncated=truncated,
    )


@router.get(
    "/runs/{run_id}/artifacts",
    response_model=RunArtifactListResponse,
    responses={404: {"model": ApiError}},
    summary="List artifacts for an optimization run",
)
async def run_artifacts(
    request: Request,
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
) -> RunArtifactListResponse:
    _get_run(request, run_id)
    records = _artifacts(request).list_for_run(run_id)
    start = (page - 1) * page_size
    return RunArtifactListResponse(
        items=[_artifact(record, request, run_id) for record in records[start : start + page_size]],
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total=len(records),
            has_next=start + page_size < len(records),
            has_previous=page > 1 and start < len(records),
        ),
    )


@router.get(
    "/runs/{run_id}/artifacts/{artifact_id}",
    response_model=Artifact,
    responses={404: {"model": ApiError}},
    summary="Return one optimization run artifact",
)
async def get_run_artifact(request: Request, run_id: str, artifact_id: str) -> Artifact:
    _get_run(request, run_id)
    record = next(
        (item for item in _artifacts(request).list_for_run(run_id) if item["id"] == artifact_id),
        None,
    )
    if record is None:
        raise _not_found("Run artifact")
    return _artifact(record, request, run_id)


@router.get(
    "/runs/{run_id}/artifacts/{artifact_id}/download",
    responses={404: {"model": ApiError}},
    summary="Download one optimization run artifact",
)
async def download_run_artifact(request: Request, run_id: str, artifact_id: str):
    _get_run(request, run_id)
    record = next(
        (item for item in _artifacts(request).list_for_run(run_id) if item["id"] == artifact_id),
        None,
    )
    if record is None or record.get("status") != "available":
        raise _not_found("Run artifact")
    path = _safe_storage_path(request, record.get("storage_key"))
    if path is None or not path.is_file():
        raise _not_found("Run artifact")
    return FileResponse(
        path,
        media_type=str(record["media_type"]),
        filename=path.name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _run_event(run_id: str, record: Mapping[str, object]) -> RunEvent:
    return RunEvent(
        id=str(record["id"]),
        run_id=run_id,
        sequence=int(record["sequence"]),
        event_type=str(record["event_type"]),
        data=dict(record.get("data") or {}),
        occurred_at=record["occurred_at"],  # type: ignore[arg-type]
    )


def _audit(
    request: Request,
    action: str,
    resource_type: str,
    resource_id: str | None,
    data: Mapping[str, object],
) -> None:
    try:
        _engine(request)
        AuditRepository(_engine(request)).append(
            action,
            resource_type,
            resource_id,
            data=data,
        )
    except Exception:
        # Operational audit failure must not change the outcome of a run
        # submission or cancellation.
        return


def _safe_storage_path(request: Request, storage_key: object) -> Path | None:
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
