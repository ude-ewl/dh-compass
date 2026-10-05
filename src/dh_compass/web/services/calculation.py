"""Application service for the redesigned one-command calculation.

The browser submits one bbox, while this service creates the internal
persistence records needed by the existing scenario, preview, and run APIs.
It intentionally does not run preprocessing or a solver in the request
handler; :mod:`dh_compass.web.jobs.calculation` continues the accepted
request asynchronously.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from dh_compass import __version__

from ..persistence.repositories import (
    CalculationRequestRepository,
    JobEventRepository,
    RunRepository,
)
from ..services.calculation_contract import (
    DEFAULT_BBOX_LIMITS,
    DEFAULT_CONFIGURATION_VERSION,
    BoundingBoxValidation,
    validate_calculation_bbox,
)
from ..services.configuration import ConfigurationAdapter
from ..services.study_area import bbox_geometry


class CalculationInputError(ValueError):
    """Raised when a bbox cannot be accepted before creating a run."""

    def __init__(self, validation: BoundingBoxValidation):
        super().__init__("The selected study area cannot be used for a calculation.")
        self.validation = validation


@dataclass(frozen=True, slots=True)
class CalculationSubmissionConflict(RuntimeError):
    """A stable conflict raised while resolving an idempotent submission."""

    code: str
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class CalculationSubmission:
    """The accepted run and the canonical bbox used to create it."""

    run: dict[str, Any]
    bbox: tuple[float, float, float, float]
    idempotency_replayed: bool


class CalculationSubmissionService:
    """Create the internal records for one accepted calculation command."""

    def __init__(self, engine: Engine, project_root: str):
        self.engine = engine
        self.project_root = project_root

    def submit(
        self,
        value: Any,
        *,
        idempotency_key: str,
    ) -> CalculationSubmission:
        validation = validate_calculation_bbox(value, limits=DEFAULT_BBOX_LIMITS)
        if not validation.valid or validation.bbox is None:
            raise CalculationInputError(validation)
        bbox = validation.bbox
        requests = CalculationRequestRepository(self.engine)
        runs = RunRepository(self.engine)

        existing = requests.get(idempotency_key)
        if existing is not None:
            return self._replay_or_conflict(existing, bbox, runs)

        adapter = ConfigurationAdapter(self.project_root)
        document = adapter.defaults
        scenario_document = document.setdefault("scenario", {})
        if not isinstance(scenario_document, dict):  # pragma: no cover - canonical defaults
            raise ValueError("The server default scenario configuration is malformed.")
        scenario_document["bbox"] = list(bbox)
        # Revalidate the detached, complete document so the persisted revision
        # is exactly the server-owned effective default snapshot.
        effective = adapter.validate(document, replace=True)

        try:
            run_id = requests.create_submission(
                idempotency_key,
                list(bbox),
                configuration_snapshot=effective.document,
                expert_override_count=effective.expert_override_count,
                configuration_version=DEFAULT_CONFIGURATION_VERSION,
                application_version=__version__,
                display_geometry=bbox_geometry(list(bbox)),
            )
        except IntegrityError:
            # The idempotency key and every internal record are committed in
            # one transaction. A uniqueness race can therefore only expose a
            # complete accepted run, never a durable partial reservation.
            existing = requests.get(idempotency_key)
            if existing is None:  # pragma: no cover - defensive database race
                raise
            return self._replay_or_conflict(existing, bbox, runs)

        run = runs.update_status(
            run_id,
            "queued",
            stage="checking_input_data",
            progress={
                "stage": "checking_input_data",
                "completed": 0,
                "total": 4,
                "fraction": None,
            },
        )
        JobEventRepository(self.engine).append_ordered(
            run_id,
            "run",
            "job.status_changed",
            {"status": "queued"},
        )
        return CalculationSubmission(run=run, bbox=bbox, idempotency_replayed=False)

    @staticmethod
    def _replay_or_conflict(
        existing: Mapping[str, Any],
        bbox: tuple[float, float, float, float],
        runs: RunRepository,
    ) -> CalculationSubmission:
        stored = existing.get("bbox")
        try:
            stored_bbox = tuple(float(value) for value in stored)
        except (TypeError, ValueError):
            stored_bbox = ()
        if stored_bbox != bbox:
            raise CalculationSubmissionConflict(
                code="IDEMPOTENCY_KEY_REUSED",
                message="The idempotency key belongs to a different bounding box.",
                details={
                    "original_bbox": list(stored_bbox),
                    "submitted_bbox": list(bbox),
                },
            )
        run_id = existing.get("run_id")
        if not run_id:
            raise CalculationSubmissionConflict(
                code="CALCULATION_SUBMISSION_IN_PROGRESS",
                message="The calculation submission is still being accepted. Retry with the same key.",
                details={},
            )
        try:
            run = runs.get(str(run_id))
        except LookupError as exc:  # pragma: no cover - protects a damaged metadata store
            raise CalculationSubmissionConflict(
                code="CALCULATION_RECORD_UNAVAILABLE",
                message="The accepted calculation record is unavailable. Retry with the same key.",
                details={},
            ) from exc
        return CalculationSubmission(run=run, bbox=bbox, idempotency_replayed=True)


def accepted_response(submission: CalculationSubmission) -> dict[str, Any]:
    """Build the small public response without exposing internal IDs."""

    run = submission.run
    status = str(run.get("status") or "queued")
    # The public calculation contract deliberately has a smaller vocabulary
    # than the internal cooperative-cancellation state.
    if status == "cancellation_requested":
        status = "running"
    return {
        "run_id": str(run["id"]),
        "status": status,
        "status_url": f"/api/v1/runs/{quote(str(run['id']), safe='')}",
        "bbox": list(submission.bbox),
        "configuration_version": str(
            run.get("configuration_version") or DEFAULT_CONFIGURATION_VERSION
        ),
        "submitted_at": run.get("created_at"),
        "idempotency_replayed": submission.idempotency_replayed,
    }


__all__ = [
    "CalculationInputError",
    "CalculationSubmission",
    "CalculationSubmissionConflict",
    "CalculationSubmissionService",
    "accepted_response",
]
