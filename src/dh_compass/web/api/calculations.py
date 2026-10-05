"""The redesigned one-command calculation API."""

from __future__ import annotations

import threading
from collections.abc import Mapping

from fastapi import APIRouter, Header, HTTPException, Request, status

from ..jobs.calculation import CalculationJobManager
from ..jobs.preview import run_preview_worker
from ..jobs.run import run_run_worker
from ..persistence.repositories import JobEventRepository, RunRepository
from ..schemas import (
    ApiError,
    CalculationAccepted,
    CalculationContractResponse,
    CalculationCreate,
)
from ..services.calculation import (
    CalculationInputError,
    CalculationSubmissionConflict,
    CalculationSubmissionService,
    accepted_response,
)
from ..services.calculation_contract import calculation_contract
from .projects import _engine

router = APIRouter(tags=["calculations"])


@router.get(
    "/calculations/contract",
    response_model=CalculationContractResponse,
    summary="Return the calculation command contract",
)
async def get_calculation_contract() -> CalculationContractResponse:
    """Return server-owned bbox, defaults, idempotency, and lifecycle rules."""

    return CalculationContractResponse(**calculation_contract())


@router.post(
    "/calculations",
    response_model=CalculationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={400: {"model": ApiError}, 409: {"model": ApiError}, 422: {"model": ApiError}},
    summary="Accept one bbox and queue its calculation",
)
async def create_calculation(
    request: Request,
    payload: CalculationCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CalculationAccepted:
    """Accept a bbox and queue the server-owned calculation lifecycle.

    Only the inexpensive bbox contract is evaluated in the request. Dataset
    validation, candidate generation, and optimization remain asynchronous so
    the browser receives one durable run identity immediately.
    """

    key = (idempotency_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "IDEMPOTENCY_KEY_REQUIRED",
                "message": "An Idempotency-Key is required to start a calculation.",
            },
        )
    if len(key) > 200:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "IDEMPOTENCY_KEY_INVALID",
                "message": "The Idempotency-Key must be at most 200 characters.",
            },
        )

    lock = getattr(request.app.state, "calculation_submission_lock", None)
    if lock is None:
        lock = threading.RLock()
        request.app.state.calculation_submission_lock = lock

    service = CalculationSubmissionService(
        _engine(request),
        request.app.state.settings.project_root,
    )
    try:
        # The lock covers the small persistence composition only. It is never
        # held while data validation, multiprocessing, or optimization runs.
        with lock:
            submission = service.submit(payload.bbox, idempotency_key=key)
    except CalculationInputError as exc:
        issues = [issue.as_dict() for issue in exc.validation.issues]
        field_errors = [
            {
                "path": issue.path,
                "message": issue.message,
                "code": issue.code,
            }
            for issue in exc.validation.issues
        ]
        first_code = exc.validation.issues[0].code if len(exc.validation.issues) == 1 else "BBOX_VALIDATION_FAILED"
        raise HTTPException(
            status_code=422,
            detail={
                "code": first_code,
                "message": "The selected study area cannot be used for a calculation.",
                "field_errors": field_errors,
                "details": {
                    "issues": issues,
                    "area_km2": exc.validation.area_km2,
                },
            },
        ) from exc
    except CalculationSubmissionConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        ) from exc

    if not submission.idempotency_replayed:
        manager = getattr(request.app.state, "calculation_job_manager", None)
        if manager is None or not callable(getattr(manager, "start", None)):
            manager = CalculationJobManager(request.app.state.settings)
            request.app.state.calculation_job_manager = manager
        try:
            manager.start(
                run_id=str(submission.run["id"]),
                scenario_id=str(submission.run["scenario_id"]),
                scenario_revision_id=str(submission.run["scenario_revision_id"]),
                configuration_snapshot=submission.run["configuration_snapshot"],
                preview_manager=request.app.state.preview_job_manager,
                run_manager=request.app.state.run_job_manager,
                refreshers=(
                    request.app.state.cache_refreshers
                    if isinstance(getattr(request.app.state, "cache_refreshers", None), Mapping)
                    else None
                ),
                preview_worker_target=(
                    getattr(request.app.state, "preview_worker_target", None) or run_preview_worker
                ),
                run_worker_target=(
                    getattr(request.app.state, "run_worker_target", None) or run_run_worker
                ),
            )
        except Exception as exc:  # noqa: BLE001 - acceptance must retain a failed run
            # Acceptance already created the immutable run. Preserve that
            # record and make launch failure visible at its status URL.
            engine = _engine(request)
            runs = RunRepository(engine)
            failed = runs.update_status(
                str(submission.run["id"]),
                "failed",
                stage="checking_input_data",
                failure_summary="The calculation worker could not be started.",
                failure_details={
                    "code": "CALCULATION_WORKER_UNAVAILABLE",
                    "error": str(exc),
                },
            )
            JobEventRepository(engine).append_ordered(
                str(submission.run["id"]),
                "run",
                "job.failed",
                {"code": "CALCULATION_WORKER_UNAVAILABLE", "message": str(exc)},
            )
            submission = type(submission)(
                run=failed,
                bbox=submission.bbox,
                idempotency_replayed=False,
            )

    return CalculationAccepted(**accepted_response(submission))


__all__ = ["router"]
