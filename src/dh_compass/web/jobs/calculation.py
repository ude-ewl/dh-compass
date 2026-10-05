"""Asynchronous orchestration for the redesigned calculation command.

A calculation is accepted after the cheap bbox contract has passed.  The
orchestrator then validates datasets, creates candidate artifacts through the
existing preview worker, and hands the same immutable run to the existing
optimization worker.  The run row remains the single status URL throughout
that lifecycle.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from ..persistence.database import create_metadata_engine
from ..persistence.migrations import run_migrations
from ..persistence.repositories import (
    DatasetStateRepository,
    JobEventRepository,
    MetadataNotFound,
    PreviewRepository,
    RunRepository,
    ScenarioRepository,
)
from ..services.configuration import ConfigurationAdapter
from ..services.data_readiness import DataReadinessService, DatasetValidationError
from ..settings import WebSettings
from .preview import PreviewJobManager, PreviewJobProcessError, run_preview_worker
from .run import RunJobManager, RunJobProcessError, run_run_worker


class CalculationJobProcessError(RuntimeError):
    """Raised when an accepted calculation cannot be scheduled."""


class CalculationJobManager:
    """Coordinate the preflight, preview, and optimization workers."""

    def __init__(self, settings: WebSettings):
        self.settings = settings
        self._jobs: dict[str, threading.Thread] = {}
        self._lock = threading.RLock()

    def start(
        self,
        *,
        run_id: str,
        scenario_id: str,
        scenario_revision_id: str,
        configuration_snapshot: Mapping[str, Any],
        preview_manager: PreviewJobManager,
        run_manager: RunJobManager,
        refreshers: Mapping[str, Callable[..., Any]] | None = None,
        preview_worker_target: Callable[..., Any] = run_preview_worker,
        run_worker_target: Callable[..., Any] = run_run_worker,
    ) -> bool:
        """Start orchestration without blocking the HTTP request."""

        with self._lock:
            if run_id in self._jobs:
                raise CalculationJobProcessError(
                    f"Calculation {run_id} is already being orchestrated."
                )
            thread = threading.Thread(
                target=self._execute,
                kwargs={
                    "run_id": run_id,
                    "scenario_id": scenario_id,
                    "scenario_revision_id": scenario_revision_id,
                    "configuration_snapshot": dict(configuration_snapshot),
                    "preview_manager": preview_manager,
                    "run_manager": run_manager,
                    "refreshers": refreshers,
                    "preview_worker_target": preview_worker_target,
                    "run_worker_target": run_worker_target,
                },
                name=f"dh-compass-calculation-{run_id}",
                daemon=True,
            )
            self._jobs[run_id] = thread
            thread.start()
            return True

    def recover(
        self,
        *,
        preview_manager: PreviewJobManager,
        run_manager: RunJobManager,
        refreshers: Mapping[str, Callable[..., Any]] | None = None,
        preview_worker_target: Callable[..., Any] = run_preview_worker,
        run_worker_target: Callable[..., Any] = run_run_worker,
    ) -> None:
        """Resume accepted queued calculation orchestration after API startup."""

        engine = create_metadata_engine(self.settings)
        try:
            run_migrations(engine)
            runs = RunRepository(engine)
            scenarios = ScenarioRepository(
                engine, ConfigurationAdapter(self.settings.project_root)
            )
            for run in runs.list_by_status(("queued",)):
                if run.get("execution_mode") != "calculation":
                    continue
                try:
                    scenario = scenarios.get(str(run["scenario_id"]))
                    self.start(
                        run_id=str(run["id"]),
                        scenario_id=str(run["scenario_id"]),
                        scenario_revision_id=str(run["scenario_revision_id"]),
                        configuration_snapshot=scenario["revision"]["document"],
                        preview_manager=preview_manager,
                        run_manager=run_manager,
                        refreshers=refreshers,
                        preview_worker_target=preview_worker_target,
                        run_worker_target=run_worker_target,
                    )
                except (MetadataNotFound, CalculationJobProcessError):
                    continue
        finally:
            engine.dispose()

    def is_running(self, run_id: str) -> bool:
        with self._lock:
            thread = self._jobs.get(run_id)
            return bool(thread and thread.is_alive())

    def _execute(
        self,
        *,
        run_id: str,
        scenario_id: str,
        scenario_revision_id: str,
        configuration_snapshot: Mapping[str, Any],
        preview_manager: PreviewJobManager,
        run_manager: RunJobManager,
        refreshers: Mapping[str, Callable[..., Any]] | None,
        preview_worker_target: Callable[..., Any],
        run_worker_target: Callable[..., Any],
    ) -> None:
        engine = create_metadata_engine(self.settings)
        try:
            run_migrations(engine)
            runs = RunRepository(engine)
            previews = PreviewRepository(engine)
            events = JobEventRepository(engine)
            adapter = ConfigurationAdapter(self.settings.project_root)
            scenario = ScenarioRepository(engine, adapter).get(scenario_id)
            if str(scenario.get("current_revision_id")) != scenario_revision_id:
                self._fail(
                    runs,
                    events,
                    run_id,
                    stage="checking_input_data",
                    summary="The calculation configuration changed before it started.",
                    details={
                        "code": "CALCULATION_REVISION_CHANGED",
                        "expected_revision_id": scenario_revision_id,
                        "current_revision_id": scenario.get("current_revision_id"),
                    },
                )
                return

            if self._cancelled(runs, run_id):
                return
            self._stage(
                runs,
                events,
                run_id,
                "checking_input_data",
                completed=0,
                fraction=None,
            )
            readiness = DataReadinessService(
                adapter,
                DatasetStateRepository(engine),
                project_root=self.settings.project_root,
                refreshers=refreshers,
            )
            try:
                descriptors, blocking, ready = self._readiness_with_managed_refresh(
                    readiness,
                    scenario,
                    refreshers,
                )
            except DatasetValidationError as exc:
                self._fail(
                    runs,
                    events,
                    run_id,
                    stage="checking_input_data",
                    summary="The configured input data could not be validated.",
                    details={
                        "code": "DATASET_VALIDATION_FAILED",
                        "error": str(exc),
                    },
                )
                return
            data_snapshot = _data_snapshot(descriptors)
            runs.set_data_snapshot(run_id, data_snapshot)
            warnings = _descriptor_issues(descriptors, include_errors=True)
            if not ready:
                self._fail(
                    runs,
                    events,
                    run_id,
                    stage="checking_input_data",
                    summary="Required input data is not ready for this study area.",
                    details={
                        "code": "DATA_NOT_READY",
                        "issues": [issue.model_dump(mode="json") for issue in blocking],
                    },
                    warnings=warnings,
                )
                return
            if self._cancelled(runs, run_id):
                return
            self._stage(
                runs,
                events,
                run_id,
                "preparing_area",
                completed=1,
                fraction=None,
                warnings=warnings,
            )

            preview_id = self._existing_preview_id(runs, run_id)
            preview = None
            if preview_id:
                try:
                    preview = previews.get(preview_id)
                except MetadataNotFound:
                    preview = None
            if preview is None:
                threshold = _threshold(configuration_snapshot)
                preview = previews.create(
                    scenario_id,
                    scenario_revision_id,
                    threshold=threshold,
                    status="queued",
                )
                runs.set_preview_id(run_id, str(preview["id"]))
                preview_id = str(preview["id"])

            if preview["status"] not in {"ready", "failed", "cancelled", "stale"}:
                self._stage(
                    runs,
                    events,
                    run_id,
                    "finding_candidates",
                    completed=2,
                    fraction=None,
                    warnings=warnings,
                )
                try:
                    if not preview_manager.is_running(preview_id):
                        preview_manager.start(
                            preview_id=preview_id,
                            scenario_id=scenario_id,
                            scenario_revision_id=scenario_revision_id,
                            document=configuration_snapshot,
                            worker_target=preview_worker_target,
                        )
                except PreviewJobProcessError as exc:
                    self._fail(
                        runs,
                        events,
                        run_id,
                        stage="finding_candidates",
                        summary="Candidate generation could not be started.",
                        details={
                            "code": "CANDIDATE_WORKER_UNAVAILABLE",
                            "error": str(exc),
                        },
                        warnings=warnings,
                    )
                    return

                preview = self._wait_for_preview(
                    runs,
                    previews,
                    preview_manager,
                    run_id,
                    preview_id,
                )
                if preview is None:
                    return

            if preview["status"] != "ready":
                code = (
                    "CANDIDATE_GENERATION_CANCELLED"
                    if preview["status"] == "cancelled"
                    else "CANDIDATE_GENERATION_FAILED"
                )
                self._fail(
                    runs,
                    events,
                    run_id,
                    stage="finding_candidates",
                    summary=preview.get("failure_summary")
                    or "Candidate generation did not complete.",
                    details={
                        "code": code,
                        "preview_id": preview_id,
                        "preview_status": preview["status"],
                    },
                    warnings=warnings + _preview_warnings(preview),
                )
                return

            final_warnings = warnings + _preview_warnings(preview)
            self._stage(
                runs,
                events,
                run_id,
                "optimizing_network",
                completed=3,
                fraction=None,
                warnings=final_warnings,
            )
            if self._cancelled(runs, run_id):
                return
            # From this point the regular run manager owns the worker and its
            # cancellation/heartbeat behavior.  Its scheduler may now also
            # pick the run if the configured concurrency is full at this exact
            # moment.
            runs.set_execution_mode(run_id, "standard")
            try:
                started = run_manager.start(
                    run_id=run_id,
                    scenario_id=scenario_id,
                    scenario_revision_id=scenario_revision_id,
                    preview_id=preview_id,
                    configuration_snapshot=dict(configuration_snapshot),
                    worker_target=run_worker_target,
                )
            except RunJobProcessError as exc:
                self._fail(
                    runs,
                    events,
                    run_id,
                    stage="optimizing_network",
                    summary="The optimization worker could not be started.",
                    details={"code": "RUN_WORKER_UNAVAILABLE", "error": str(exc)},
                    warnings=final_warnings,
                )
                return
            if not started:
                events.append_ordered(
                    run_id,
                    "run",
                    "calculation.stage_completed",
                    {"stage": "finding_candidates", "status": "queued"},
                )
        except Exception as exc:  # noqa: BLE001 - async boundary must persist failure
            try:
                self._fail(
                    RunRepository(engine),
                    JobEventRepository(engine),
                    run_id,
                    stage="checking_input_data",
                    summary="The calculation could not be prepared.",
                    details={
                        "code": "CALCULATION_ORCHESTRATION_FAILED",
                        "exception_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
            except Exception:
                # A database failure cannot be repaired from the worker thread.
                pass
        finally:
            engine.dispose()
            with self._lock:
                self._jobs.pop(run_id, None)

    def _wait_for_preview(
        self,
        runs: RunRepository,
        previews: PreviewRepository,
        preview_manager: PreviewJobManager,
        run_id: str,
        preview_id: str,
    ) -> dict[str, Any] | None:
        while True:
            current_run = runs.get(run_id)
            if current_run["status"] in {
                "cancelled",
                "failed",
                "cancellation_requested",
            }:
                if preview_manager.is_running(preview_id):
                    preview_manager.cancel(preview_id)
                return None
            preview = previews.get(preview_id)
            if preview["status"] in {"ready", "failed", "cancelled", "stale"}:
                return preview
            time.sleep(0.25)

    @classmethod
    def _readiness_with_managed_refresh(
        cls,
        readiness: DataReadinessService,
        scenario: Mapping[str, Any],
        refreshers: Mapping[str, Callable[..., Any]] | None,
    ) -> tuple[list[Any], list[Any], bool]:
        """Refresh configured missing caches once, then validate the result.

        A calculation has only a bbox as user input, so its managed cache is
        part of the server-owned preparation lifecycle.  The download remains
        limited to explicitly registered refresh providers.
        """
        descriptors, blocking, ready = readiness.readiness(scenario)
        if ready or not cls._refresh_missing_managed_caches(
            readiness, scenario, blocking, refreshers
        ):
            return descriptors, blocking, ready
        return readiness.readiness(scenario)

    @staticmethod
    def _refresh_missing_managed_caches(
        readiness: DataReadinessService,
        scenario: Mapping[str, Any],
        blocking: list[Any],
        refreshers: Mapping[str, Callable[..., Any]] | None,
    ) -> bool:
        """Prepare missing managed caches independently of static input errors.

        Unsupported issues remain blocking when readiness is checked again;
        they must not suppress downloads for other, refreshable datasets.
        """
        if not refreshers:
            return False
        managed_refreshes: list[tuple[str, Callable[..., Any]]] = []
        scheduled: set[str] = set()
        for issue in blocking:
            dataset_id = getattr(issue, "path", None)
            code = getattr(issue, "code", None)
            if code != "DATASET_MISSING" and not (
                dataset_id == "weather" and code == "DATASET_SCHEMA_INVALID"
            ):
                continue
            if not isinstance(dataset_id, str):
                continue
            provider = refreshers.get(dataset_id)
            if not callable(provider) or dataset_id in scheduled:
                continue
            managed_refreshes.append((dataset_id, provider))
            scheduled.add(dataset_id)
        for dataset_id, provider in managed_refreshes:
            readiness.refresh(scenario, dataset_id, provider=provider)
        return bool(managed_refreshes)

    @staticmethod
    def _existing_preview_id(runs: RunRepository, run_id: str) -> str | None:
        run = runs.get(run_id)
        value = run.get("preview_id")
        return str(value) if value else None

    @staticmethod
    def _cancelled(runs: RunRepository, run_id: str) -> bool:
        return runs.get(run_id)["status"] in {
            "cancelled",
            "failed",
            "cancellation_requested",
        }

    @staticmethod
    def _stage(
        runs: RunRepository,
        events: JobEventRepository,
        run_id: str,
        stage: str,
        *,
        completed: int,
        fraction: float | None,
        warnings: list[dict[str, Any]] | None = None,
    ) -> None:
        runs.update_status(
            run_id,
            "queued",
            stage=stage,
            progress={
                "stage": stage,
                "completed": completed,
                "total": 4,
                "fraction": fraction,
            },
            warnings=warnings,
        )
        events.append_ordered(
            run_id,
            "run",
            "calculation.stage_started",
            {"stage": stage},
        )

    @staticmethod
    def _fail(
        runs: RunRepository,
        events: JobEventRepository,
        run_id: str,
        *,
        stage: str,
        summary: str,
        details: Mapping[str, Any],
        warnings: list[dict[str, Any]] | None = None,
    ) -> None:
        current = runs.get(run_id)
        if current["status"] in {"completed", "failed", "cancelled"}:
            return
        runs.update_status(
            run_id,
            "failed",
            stage=stage,
            failure_summary=summary,
            failure_details=details,
            warnings=warnings,
        )
        events.append_ordered(
            run_id,
            "run",
            "job.failed",
            {"message": summary, **dict(details)},
        )


def _threshold(document: Mapping[str, Any]) -> float | None:
    network = document.get("network")
    if not isinstance(network, Mapping):
        return None
    value = network.get("linear_heat_density_threshold")
    return float(value) if value is not None else None


def _data_snapshot(descriptors: list[Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for descriptor in descriptors:
        serialized = descriptor.model_dump(mode="json")
        values[str(descriptor.id)] = {
            "status": serialized.get("status"),
            "metadata": serialized.get("metadata") or {},
            "extent": serialized.get("extent"),
            "checked_at": serialized.get("checked_at"),
        }
    return {"datasets": values}


def _descriptor_issues(
    descriptors: list[Any], *, include_errors: bool = False
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for descriptor in descriptors:
        for issue in descriptor.issues:
            if include_errors or issue.severity != "error":
                values.append(issue.model_dump(mode="json"))
    return values


def _preview_warnings(preview: Mapping[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for issue in preview.get("warnings") or []:
        if isinstance(issue, Mapping):
            values.append(dict(issue))
    return values


__all__ = [
    "CalculationJobManager",
    "CalculationJobProcessError",
]
