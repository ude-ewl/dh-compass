"""Comparison endpoints for completed planning runs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..persistence.repositories import (
    AuditRepository,
    ComparisonRepository,
    MetadataNotFound,
)
from ..schemas import ApiError, ComparisonCreate, ComparisonResource
from ..services.comparison import ComparisonInputError, ComparisonService
from .projects import _engine
from .results import _discovery

router = APIRouter(tags=["comparison"])


def _resource(record: dict) -> ComparisonResource:
    result = record.get("result") if isinstance(record.get("result"), dict) else {}
    kpis = list(result.get("kpi_differences", result.get("kpis", [])))
    configuration = list(
        result.get("configuration_changes", result.get("configuration", []))
    )
    supply = list(result.get("supply", result.get("portfolio", [])))
    costs = list(result.get("costs", result.get("cost_differences", [])))
    return ComparisonResource(
        id=str(record["id"]),
        run_ids=[str(item) for item in record.get("run_ids", [])],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        compatibility=result.get("compatibility", []),
        compatible=bool(result.get("compatible", False)),
        baseline_run_id=result.get("baseline_run_id"),
        warnings=list(result.get("warnings", [])),
        runs=list(result.get("runs", [])),
        kpi_differences=kpis,
        kpis=kpis,
        configuration_changes=configuration,
        configuration=configuration,
        network=dict(result.get("network", {})),
        supply=supply,
        portfolio=supply,
        costs=costs,
        cost_differences=costs,
    )


def _service(request: Request) -> ComparisonService:
    return ComparisonService(_discovery(request), engine=_engine(request))


@router.post(
    "/comparisons",
    response_model=ComparisonResource,
    status_code=201,
    responses={400: {"model": ApiError}, 404: {"model": ApiError}, 409: {"model": ApiError}},
    summary="Compare two to four completed runs",
)
async def create_comparison(request: Request, payload: ComparisonCreate) -> ComparisonResource:
    try:
        result = _service(request).compare(
            payload.run_ids,
            include_unchanged_configuration=payload.include_unchanged_configuration,
        )
    except ComparisonInputError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "COMPARISON_NOT_AVAILABLE",
                "message": str(exc),
                "details": exc.details,
            },
        ) from exc

    record = ComparisonRepository(_engine(request)).create(payload.run_ids, result)
    try:
        AuditRepository(_engine(request)).append(
            "comparison.created",
            "comparison",
            record["id"],
            data={"run_ids": payload.run_ids},
        )
    except Exception:
        # Audit persistence must never turn a valid comparison into a failed
        # response, especially when reading an old metadata database.
        pass
    return _resource(record)


@router.get(
    "/comparisons/{comparison_id}",
    response_model=ComparisonResource,
    responses={404: {"model": ApiError}},
    summary="Return a persisted run comparison",
)
async def get_comparison(request: Request, comparison_id: str) -> ComparisonResource:
    try:
        record = ComparisonRepository(_engine(request)).get(comparison_id)
    except MetadataNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Comparison was not found."},
        ) from exc
    return _resource(record)


__all__ = ["router"]
