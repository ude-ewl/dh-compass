"""Report, CSV, and reproducibility bundle endpoints."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from ..persistence.repositories import AuditRepository, ExportJobRepository, MetadataNotFound
from ..schemas import (
    ApiError,
    ExportCreate,
    ExportJobResource,
    RetentionCleanupResponse,
)
from ..services.exports import ExportInputError, ExportService, RetentionService
from .projects import _engine
from .results import _discovery

router = APIRouter(tags=["exports"])


def _service(request: Request) -> ExportService:
    settings = request.app.state.settings
    return ExportService(
        _discovery(request),
        output_root=settings.output_root,
        project_root=settings.project_root,
        engine=_engine(request),
    )


def _resource(record: dict) -> ExportJobResource:
    status = str(record.get("status", "queued"))
    download_url = (
        f"/api/v1/exports/{quote(str(record['id']), safe='')}/download"
        if status == "available"
        else None
    )
    return ExportJobResource(
        id=str(record["id"]),
        run_id=str(record["run_id"]),
        kind=status_kind(record.get("kind")),
        status=status,  # type: ignore[arg-type]
        display_name=str(record["display_name"]),
        media_type=str(record["media_type"]),
        byte_size=record.get("byte_size"),
        checksum_sha256=record.get("checksum_sha256"),
        download_url=download_url,
        error=record.get("error"),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


def status_kind(value: object) -> str:
    value = str(value or "report")
    return value if value in {"report", "bundle", "csv"} else "report"


def _not_found(kind: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"{kind} was not found."},
    )


def _export_error(exc: ExportInputError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "EXPORT_NOT_AVAILABLE",
            "message": str(exc),
        },
    )


@router.post(
    "/runs/{run_id:path}/reports",
    response_model=ExportJobResource,
    status_code=202,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}},
    summary="Generate a printable run report",
)
async def create_report(
    request: Request,
    run_id: str,
    background_tasks: BackgroundTasks,
    payload: ExportCreate | None = None,
) -> ExportJobResource:
    del payload
    service = _service(request)
    try:
        record = service.enqueue(run_id, "report")
    except ExportInputError as exc:
        raise _export_error(exc) from exc
    background_tasks.add_task(service.generate, str(record["id"]))
    _audit(request, "export.report_requested", run_id, {"export_id": record["id"]})
    return _resource(record)


@router.post(
    "/runs/{run_id:path}/bundles",
    response_model=ExportJobResource,
    status_code=202,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}},
    summary="Generate a reproducibility bundle",
)
async def create_bundle(
    request: Request,
    run_id: str,
    background_tasks: BackgroundTasks,
    payload: ExportCreate | None = None,
) -> ExportJobResource:
    del payload
    service = _service(request)
    try:
        record = service.enqueue(run_id, "bundle")
    except ExportInputError as exc:
        raise _export_error(exc) from exc
    background_tasks.add_task(service.generate, str(record["id"]))
    _audit(request, "export.bundle_requested", run_id, {"export_id": record["id"]})
    return _resource(record)


@router.get(
    "/runs/{run_id:path}/exports/{table}.csv",
    responses={404: {"model": ApiError}, 409: {"model": ApiError}},
    summary="Export a result table as CSV",
)
async def export_csv(request: Request, run_id: str, table: str) -> Response:
    service = _service(request)
    try:
        content = service.csv_bytes(run_id, table)
        normalized = service.normalize_table(table)
    except ExportInputError as exc:
        raise _export_error(exc) from exc
    _audit(request, "export.csv_requested", run_id, {"table": normalized})
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{normalized}.csv"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/runs/{run_id:path}/exports/{table}",
    include_in_schema=False,
)
async def export_csv_without_suffix(request: Request, run_id: str, table: str) -> Response:
    return await export_csv(request, run_id, table)


@router.post(
    "/runs/{run_id:path}/exports/csv",
    response_model=ExportJobResource,
    status_code=202,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}},
    summary="Queue a durable CSV export",
)
async def create_csv_export(
    request: Request,
    run_id: str,
    background_tasks: BackgroundTasks,
    payload: ExportCreate | None = None,
) -> ExportJobResource:
    service = _service(request)
    try:
        record = service.enqueue(
            run_id,
            "csv",
            table=payload.table if payload is not None else None,
        )
    except ExportInputError as exc:
        raise _export_error(exc) from exc
    background_tasks.add_task(service.generate, str(record["id"]))
    _audit(
        request,
        "export.csv_requested",
        run_id,
        {"export_id": record["id"], "table": record.get("metadata", {}).get("table")},
    )
    return _resource(record)


@router.get(
    "/runs/{run_id:path}/exports",
    response_model=list[ExportJobResource],
    responses={404: {"model": ApiError}},
    summary="List generated exports for a run",
)
async def list_exports(request: Request, run_id: str) -> list[ExportJobResource]:
    # Validate the run through the same safe root boundary before exposing job
    # metadata.  This also supports legacy output IDs containing a slash.
    try:
        _service(request)._resolve_completed_run(run_id)
    except ExportInputError as exc:
        raise _export_error(exc) from exc
    return [_resource(item) for item in ExportJobRepository(_engine(request)).list_for_run(run_id)]


@router.post(
    "/maintenance/retention/cleanup",
    response_model=RetentionCleanupResponse,
    summary="Remove old generated exports without deleting run artifacts",
)
async def cleanup_exports(
    request: Request,
    older_than_days: int | None = Query(default=None, ge=0),
    dry_run: bool = Query(default=False),
) -> RetentionCleanupResponse:
    settings = request.app.state.settings
    age = settings.artifact_retention_days if older_than_days is None else older_than_days
    result = RetentionService(settings.output_root, _engine(request)).cleanup(
        older_than_days=age,
        dry_run=dry_run,
    )
    _audit(
        request,
        "export.retention_cleanup",
        "output_root",
        result,
        resource_type="maintenance",
    )
    return RetentionCleanupResponse(**result)


@router.get(
    "/exports/{export_id}",
    response_model=ExportJobResource,
    responses={404: {"model": ApiError}},
    summary="Return export generation status",
)
async def get_export(request: Request, export_id: str) -> ExportJobResource:
    try:
        record = ExportJobRepository(_engine(request)).get(export_id)
    except MetadataNotFound as exc:
        raise _not_found("Export") from exc
    return _resource(record)


@router.get(
    "/exports/{export_id}/download",
    responses={404: {"model": ApiError}},
    summary="Download a generated export",
)
async def download_export(request: Request, export_id: str):
    try:
        record = ExportJobRepository(_engine(request)).get(export_id)
    except MetadataNotFound as exc:
        raise _not_found("Export") from exc
    if record.get("status") != "available":
        raise _not_found("Export")
    try:
        path = _service(request).get_path(record)
    except FileNotFoundError as exc:
        raise _not_found("Export") from exc
    _audit(request, "export.downloaded", str(record["run_id"]), {"export_id": export_id})
    return FileResponse(
        path,
        media_type=str(record["media_type"]),
        filename=str(record["display_name"]),
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _audit(
    request: Request,
    action: str,
    resource_id: str,
    data: dict,
    *,
    resource_type: str = "run",
) -> None:
    try:
        AuditRepository(_engine(request)).append(
            action,
            resource_type,
            resource_id,
            data=data,
        )
    except Exception:
        # Export availability must not depend on optional audit cleanup.
        return


__all__ = ["router"]
