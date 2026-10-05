"""Dataset readiness, metadata, and managed cache endpoints."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..persistence.repositories import DatasetStateRepository, MetadataNotFound
from ..schemas import (
    ApiError,
    DatasetDescriptor,
    DatasetLayerResponse,
    DatasetRefreshRequest,
    DatasetRefreshResponse,
    DatasetValidationRequest,
    DatasetValidationResponse,
)
from ..services.data_readiness import (
    CacheRefreshUnavailable,
    DataReadinessService,
    DatasetValidationError,
)
from .projects import _adapter, _engine, _not_found, _scenarios

router = APIRouter(tags=["datasets"])


def _service(request: Request) -> DataReadinessService:
    refreshers = getattr(request.app.state, "cache_refreshers", {})
    return DataReadinessService(
        _adapter(request),
        DatasetStateRepository(_engine(request)),
        project_root=request.app.state.settings.project_root,
        refreshers=refreshers if isinstance(refreshers, Mapping) else {},
    )


def _scenario(request: Request, scenario_id: str) -> dict[str, Any]:
    try:
        return _scenarios(request).get(scenario_id)
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc


def _readiness(request: Request, scenario_id: str, dataset_ids=None) -> DatasetValidationResponse:
    scenario = _scenario(request, scenario_id)
    try:
        descriptors, blocking, ready = _service(request).readiness(
            scenario, dataset_ids=dataset_ids
        )
    except DatasetValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "DATASET_VALIDATION_FAILED", "message": str(exc)},
        ) from exc
    from datetime import datetime, timezone

    return DatasetValidationResponse(
        scenario_id=scenario_id,
        ready=ready,
        checked_at=datetime.now(timezone.utc),
        datasets=descriptors,
        blocking_issues=blocking,
    )


@router.get(
    "/scenarios/{scenario_id}/datasets",
    response_model=DatasetValidationResponse,
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
    summary="Return readiness for all configured input datasets",
)
async def list_datasets(request: Request, scenario_id: str) -> DatasetValidationResponse:
    return _readiness(request, scenario_id)


@router.post(
    "/scenarios/{scenario_id}/datasets/validate",
    response_model=DatasetValidationResponse,
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
    summary="Validate selected datasets and return actionable issues",
)
async def validate_datasets(
    request: Request,
    scenario_id: str,
    payload: DatasetValidationRequest | None = None,
) -> DatasetValidationResponse:
    request_payload = payload or DatasetValidationRequest()
    return _readiness(request, scenario_id, request_payload.dataset_ids)


@router.get(
    "/scenarios/{scenario_id}/datasets/{dataset_id}",
    response_model=DatasetDescriptor,
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
    summary="Return one dataset descriptor",
)
async def get_dataset(request: Request, scenario_id: str, dataset_id: str):
    scenario = _scenario(request, scenario_id)
    try:
        return _service(request).validate_one(scenario, dataset_id)
    except DatasetValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "DATASET_VALIDATION_FAILED", "message": str(exc)},
        ) from exc


@router.post(
    "/scenarios/{scenario_id}/datasets/{dataset_id}/refresh",
    response_model=DatasetRefreshResponse,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}, 422: {"model": ApiError}},
    summary="Run an explicitly permitted managed cache refresh",
)
async def refresh_dataset(
    request: Request,
    scenario_id: str,
    dataset_id: str,
    payload: DatasetRefreshRequest | None = None,
) -> DatasetRefreshResponse:
    scenario = _scenario(request, scenario_id)
    refreshers = getattr(request.app.state, "cache_refreshers", {})
    provider = refreshers.get(dataset_id) if isinstance(refreshers, Mapping) else None
    try:
        descriptor = _service(request).refresh(
            scenario,
            dataset_id,
            force=bool(payload.force) if payload else False,
            provider=provider,
        )
    except CacheRefreshUnavailable as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "CACHE_REFRESH_UNAVAILABLE", "message": str(exc)},
        ) from exc
    except DatasetValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "CACHE_REFRESH_NOT_PERMITTED", "message": str(exc)},
        ) from exc
    except Exception as exc:  # noqa: BLE001 - provider boundary
        raise HTTPException(
            status_code=502,
            detail={
                "code": "CACHE_REFRESH_FAILED",
                "message": "The managed cache refresh failed.",
                "details": {"error": str(exc)},
            },
        ) from exc
    return DatasetRefreshResponse(
        scenario_id=scenario_id,
        dataset=descriptor,
        action="refreshed",
        message="The managed dataset cache was refreshed and validated.",
    )


@router.get(
    "/scenarios/{scenario_id}/datasets/{dataset_id}/layer",
    response_model=DatasetLayerResponse,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}, 422: {"model": ApiError}},
    summary="Return a bounded GeoJSON preview of one dataset",
)
async def dataset_layer(request: Request, scenario_id: str, dataset_id: str):
    scenario = _scenario(request, scenario_id)
    service = _service(request)
    try:
        definition = next(item for item in service.definitions(scenario) if item.id == dataset_id)
    except StopIteration as exc:
        raise _not_found("Dataset") from exc
    descriptor = service.validate_one(scenario, dataset_id)
    if descriptor.status not in {"ready", "stale"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DATASET_LAYER_UNAVAILABLE",
                "message": f"The {dataset_id} layer is not available.",
                "details": {"status": descriptor.status},
            },
        )
    path = definition.path
    if path is None:
        for candidate in definition.candidates:
            if candidate.exists():
                path = candidate
                break
    if path is None or definition.kind not in {"geospatial", "resource"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DATASET_LAYER_UNAVAILABLE",
                "message": "This dataset does not expose a map preview.",
            },
        )
    try:
        import geopandas as gpd

        kwargs: dict[str, Any] = {"rows": 5000}
        if definition.layer and path.suffix.lower() not in {".geojson", ".json"}:
            kwargs["layer"] = definition.layer
        frame = gpd.read_file(path, **kwargs)
        if frame.crs is not None:
            frame = frame.to_crs(4326)
        document = json.loads(frame.to_json(drop_id=False))
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "DATASET_LAYER_INVALID",
                "message": "The dataset map preview could not be read.",
                "details": {"error": str(exc)},
            },
        ) from exc
    return JSONResponse(
        content={
            "dataset_id": dataset_id,
            "source": descriptor.path_display,
            "truncated": len(document.get("features", [])) >= 5000,
            "geojson": document,
        }
    )


__all__ = ["router"]
