"""Read-only run, result, artifact, and download endpoints."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from ..persistence.repositories import MetadataNotFound, RunRepository
from ..schemas import (
    ApiError,
    ArtifactAvailability,
    ArtifactListResponse,
    Page,
    Pagination,
    ResultEnvelope,
    ResultProvenance,
    RunManifest,
)
from ..services.output_discovery import LegacyRun, OutputDiscoveryService
from ..services.result_adapter import LegacyResultAdapter

router = APIRouter(tags=["results"])


def _discovery(request: Request) -> OutputDiscoveryService:
    service = getattr(request.app.state, "output_discovery", None)
    if isinstance(service, OutputDiscoveryService):
        return service
    # This fallback keeps the route module usable with small isolated app
    # fixtures while still taking the configured path from the application.
    return OutputDiscoveryService(request.app.state.settings.output_root)


def _adapter(request: Request) -> LegacyResultAdapter:
    return LegacyResultAdapter(_discovery(request))


def _not_found(kind: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "NOT_FOUND",
            "message": f"{kind} was not found.",
        },
    )


def _result_output_id(request: Request, run_id: str) -> str:
    """Resolve a managed run UUID to its safe output storage key.

    Legacy output IDs remain the public path used by the original viewer.  A
    managed run has a separate UUID, but its completed artifacts are written
    to the same two-level output layout.  Keeping this translation in the web
    adapter preserves one result contract for both resources.
    """

    try:
        return _discovery(request).get_legacy_run(run_id).id
    except FileNotFoundError:
        pass
    engine = getattr(request.app.state, "metadata_engine", None)
    if engine is None:
        raise _not_found("Run")
    try:
        managed = RunRepository(engine).get(run_id)
    except MetadataNotFound as exc:
        raise _not_found("Run") from exc
    output_id = managed.get("output_storage_key")
    if not isinstance(output_id, str) or not output_id:
        raise _not_found("Run")
    try:
        return _discovery(request).get_legacy_run(output_id).id
    except FileNotFoundError as exc:
        raise _not_found("Run") from exc


def _run(request: Request, run_id: str) -> LegacyRun:
    try:
        return _discovery(request).get_legacy_run(_result_output_id(request, run_id))
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise _not_found("Run") from exc


def _download_url(request: Request, run_id: str, artifact_id: str) -> str:
    del request
    return (
        f"/api/v1/runs/{quote(run_id, safe='')}/artifacts/"
        f"{quote(artifact_id, safe='')}/download"
    )


def _manifest(request: Request, run: LegacyRun) -> RunManifest:
    return run.to_schema(
        download_url_for=lambda run_id, artifact_id: _download_url(
            request, run_id, artifact_id
        )
    )


def _decorate_result(request: Request, run_id: str, result: ResultEnvelope) -> ResultEnvelope:
    """Attach cacheable provenance and section availability metadata."""

    run = _run(request, run_id)
    checksums = {
        artifact.id: artifact.checksum_sha256
        for artifact in run.artifacts
        if artifact.id in result.source_artifacts
    }
    availability = dict(result.availability)
    if isinstance(result.data, dict) and isinstance(result.data.get("availability"), dict):
        availability.update(
            {
                str(key): bool(value)
                for key, value in result.data["availability"].items()
            }
        )
    availability.setdefault("result", result.available)
    provenance = ResultProvenance(
        run_id=run_id,
        source_artifacts=list(result.source_artifacts),
        artifact_checksums=checksums,
        immutable=run.status == "completed",
    )
    return result.model_copy(
        update={"availability": availability, "provenance": provenance}
    )


def _result_response(request: Request, run_id: str, result: ResultEnvelope):
    """Return a result with a deterministic ETag and conditional GET support."""

    decorated = _decorate_result(request, run_id, result)
    without_hash = decorated.model_copy(update={"content_hash": None})
    canonical = json.dumps(
        without_hash.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    content_hash = hashlib.sha256(canonical).hexdigest()
    payload = decorated.model_copy(update={"content_hash": content_hash}).model_dump(mode="json")
    etag = f'"{content_hash}"'
    headers = {
        "ETag": etag,
        "X-Content-Hash": content_hash,
        "Cache-Control": "public, max-age=0, must-revalidate"
        if decorated.provenance and decorated.provenance.immutable
        else "no-cache",
    }
    supplied = request.headers.get("if-none-match", "")
    supplied_values = {value.strip().removeprefix("W/") for value in supplied.split(",")}
    if etag in supplied_values:
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=payload, headers=headers)


def _envelope(
    request: Request, adapter: LegacyResultAdapter, operation: str, run_id: str
):
    output_id = _result_output_id(request, run_id)
    return _result_response(request, run_id, getattr(adapter, operation)(output_id))


@router.get(
    "/runs",
    response_model=Page[RunManifest],
    responses={400: {"model": ApiError}, 404: {"model": ApiError}},
    summary="List discovered output runs",
)
async def list_runs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[RunManifest]:
    discovery = _discovery(request)
    runs = discovery.list_runs()
    total = len(runs)
    start = (page - 1) * page_size
    items = runs[start : start + page_size]
    manifests = [
        item.model_copy(
            update={
                "artifacts": [
                    artifact.model_copy(
                        update={
                            "download_url": (
                                _download_url(request, item.id, artifact.id)
                                if artifact.available
                                else None
                            )
                        }
                    )
                    for artifact in item.artifacts
                ]
            }
        )
        for item in items
    ]
    return Page(
        items=manifests,
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total=total,
            has_next=start + page_size < total,
            has_previous=page > 1 and start < total,
        ),
    )


# Specific result routes are declared before the path-converter manifest route.
@router.get(
    "/runs/{run_id:path}/results/summary",
    response_model=ResultEnvelope,
    responses={404: {"model": ApiError}},
    summary="Return run summary results",
)
async def get_summary(request: Request, run_id: str) -> ResultEnvelope:
    _run(request, run_id)
    return _envelope(request, _adapter(request), "summary", run_id)


@router.get(
    "/runs/{run_id:path}/results/network",
    response_model=ResultEnvelope,
    responses={404: {"model": ApiError}},
    summary="Return final and candidate network layers",
)
async def get_network(
    request: Request,
    run_id: str,
    layers: str | None = Query(default=None),
) -> ResultEnvelope:
    _run(request, run_id)
    requested_layers = _network_layers(layers)
    result = _adapter(request).network(
        _result_output_id(request, run_id), layers=requested_layers
    )
    return _result_response(request, run_id, result)


@router.get(
    "/runs/{run_id:path}/results/iterations",
    response_model=ResultEnvelope,
    responses={404: {"model": ApiError}},
    summary="Return decision playback iterations",
)
async def get_iterations(request: Request, run_id: str) -> ResultEnvelope:
    _run(request, run_id)
    return _envelope(request, _adapter(request), "iterations", run_id)


@router.get(
    "/runs/{run_id:path}/results/candidates",
    response_model=ResultEnvelope,
    responses={404: {"model": ApiError}},
    summary="Return candidate summaries",
)
async def get_candidates(request: Request, run_id: str) -> ResultEnvelope:
    _run(request, run_id)
    return _envelope(request, _adapter(request), "candidates", run_id)


@router.get(
    "/runs/{run_id:path}/results/candidates/{candidate_id}",
    response_model=ResultEnvelope,
    responses={404: {"model": ApiError}},
    summary="Return one candidate result",
)
async def get_candidate(
    request: Request, run_id: str, candidate_id: int
) -> ResultEnvelope:
    _run(request, run_id)
    result = _adapter(request).candidate(_result_output_id(request, run_id), candidate_id)
    if not result.available and any(
        warning.startswith("Candidate ") and warning.endswith(" was not found.")
        for warning in result.warnings
    ):
        raise _not_found("Candidate")
    return _result_response(request, run_id, result)


@router.get(
    "/runs/{run_id:path}/results/supply",
    response_model=ResultEnvelope,
    responses={404: {"model": ApiError}},
    summary="Return supply portfolio results",
)
async def get_supply(request: Request, run_id: str) -> ResultEnvelope:
    _run(request, run_id)
    return _envelope(request, _adapter(request), "supply", run_id)


@router.get(
    "/runs/{run_id:path}/results/costs",
    response_model=ResultEnvelope,
    responses={404: {"model": ApiError}},
    summary="Return cost results",
)
async def get_costs(request: Request, run_id: str) -> ResultEnvelope:
    _run(request, run_id)
    return _envelope(request, _adapter(request), "costs", run_id)


@router.get(
    "/runs/{run_id:path}/results/decentral",
    response_model=ResultEnvelope,
    responses={404: {"model": ApiError}, 304: {"description": "Not modified"}},
    summary="Return decentralized cluster comparison",
)
async def get_decentral(request: Request, run_id: str):
    _run(request, run_id)
    return _envelope(request, _adapter(request), "decentral", run_id)


@router.get(
    "/runs/{run_id:path}/results/timeseries",
    response_model=ResultEnvelope,
    responses={404: {"model": ApiError}, 304: {"description": "Not modified"}},
    summary="Return an optional bounded result time series",
)
async def get_timeseries(
    request: Request,
    run_id: str,
    series: str | None = Query(default=None),
    resolution: str | None = Query(default=None),
):
    _run(request, run_id)
    result = _adapter(request).timeseries(
        _result_output_id(request, run_id),
        series=series,
        max_points=_timeseries_resolution(resolution),
    )
    return _result_response(request, run_id, result)


@router.get(
    "/runs/{run_id:path}/results/performance",
    response_model=ResultEnvelope,
    responses={404: {"model": ApiError}},
    summary="Return performance diagnostics",
)
async def get_performance(request: Request, run_id: str) -> ResultEnvelope:
    _run(request, run_id)
    return _envelope(request, _adapter(request), "performance", run_id)


@router.get(
    "/runs/{run_id:path}/artifacts",
    response_model=ArtifactListResponse,
    responses={404: {"model": ApiError}},
    summary="List run artifacts",
)
async def list_artifacts(
    request: Request,
    run_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=200),
) -> ArtifactListResponse:
    run = _run(request, run_id)
    total = len(run.artifacts)
    start = (page - 1) * page_size
    records = run.artifacts[start : start + page_size]
    items = [
        artifact.to_schema(download_url=_download_url(request, run.id, artifact.id))
        for artifact in records
    ]
    return ArtifactListResponse(
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
    "/runs/{run_id:path}/artifacts/{artifact_id:path}/download",
    name="download_artifact",
    responses={404: {"model": ApiError}},
    summary="Download one run artifact",
)
async def download_artifact(request: Request, run_id: str, artifact_id: str) -> FileResponse:
    _run(request, run_id)
    try:
        path = _discovery(request).resolve_artifact(run_id, artifact_id)
    except FileNotFoundError as exc:
        raise _not_found("Artifact") from exc
    artifact = _discovery(request).get_legacy_run(run_id).artifact(artifact_id)
    media_type = artifact.media_type if artifact else None
    return FileResponse(
        path,
        media_type=media_type,
        filename=Path(path).name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get(
    "/runs/{run_id:path}/artifacts/{artifact_id:path}",
    response_model=ArtifactAvailability,
    responses={404: {"model": ApiError}},
    summary="Return artifact metadata",
)
async def get_artifact(
    request: Request, run_id: str, artifact_id: str
) -> ArtifactAvailability:
    run = _run(request, run_id)
    artifact = run.artifact(artifact_id)
    if artifact is None:
        raise _not_found("Artifact")
    return artifact.to_schema(
        download_url=(
            _download_url(request, run.id, artifact.id)
            if artifact.status == "available"
            else None
        )
    )


@router.get(
    "/runs/{run_id:path}",
    response_model=RunManifest,
    responses={404: {"model": ApiError}},
    summary="Return a run manifest",
)
async def get_legacy_run(request: Request, run_id: str) -> RunManifest:
    return _manifest(request, _run(request, run_id))


def _network_layers(value: str | None) -> set[str] | None:
    if value is None or not value.strip():
        return None
    allowed = {"final_network", "candidate_network", "lhd", "connection_paths"}
    requested = {part.strip() for part in value.split(",") if part.strip()}
    return requested & allowed


def _timeseries_resolution(value: str | None) -> int:
    if value is None or not value.strip():
        return 5_000
    try:
        return max(1, min(int(value), 100_000))
    except ValueError:
        # Named resolutions are accepted for clients that do not know the
        # source cadence.  They remain a point budget rather than a promise
        # to fabricate an interval the artifact does not contain.
        return {
            "raw": 100_000,
            "hourly": 5_000,
            "daily": 2_000,
            "weekly": 500,
        }.get(value.strip().lower(), 5_000)


__all__ = ["router"]
