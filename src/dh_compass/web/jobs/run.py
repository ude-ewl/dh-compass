"""Child-process execution for complete DH-COMPASS runs."""

from __future__ import annotations

import errno
import hashlib
import json
import multiprocessing
import os
import re
import threading
import traceback
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dh_compass import __version__, pipeline
from dh_compass.config import load_config_from_document
from dh_compass.observability.progress import (
    CancellationRequested,
    CancellationToken,
    PipelineObserver,
)

from ..persistence.database import create_metadata_engine
from ..persistence.migrations import run_migrations
from ..persistence.repositories import (
    ArtifactMetadataRepository,
    JobEventRepository,
    RunRepository,
)
from ..settings import WebSettings


class RunJobProcessError(RuntimeError):
    """Raised when a run worker cannot be launched."""


class RunCancelled(RuntimeError):
    """Compatibility exception for callers that use a worker-specific name."""


def classify_run_failure(exc: Exception) -> dict[str, Any]:
    """Return a stable, actionable failure envelope for common run failures."""

    message = str(exc).lower()
    if isinstance(exc, OSError) and (
        exc.errno == errno.ENOSPC or "no space left on device" in message
    ):
        return {
            "code": "OUTPUT_STORAGE_FULL",
            "issues": [
                {
                    "message": "The output storage is full, so this calculation could not write its results.",
                    "remediation": "Free space outside completed run folders, then start a new calculation.",
                }
            ],
        }
    if (
        (
            isinstance(exc, ModuleNotFoundError)
            and (
                exc.name in {"mip", "gurobipy"}
                or "no module named 'mip'" in message
                or "no module named 'gurobipy'" in message
            )
        )
        or "solver unavailable" in message
        or "solver license" in message
    ):
        return {
            "code": "SOLVER_UNAVAILABLE",
            "issues": [
                {
                    "message": "The optimization solver is unavailable.",
                    "remediation": "Install or configure the solver and its license, then start a new calculation.",
                }
            ],
        }
    return {
        "code": "RUN_WORKER_FAILED",
        "issues": [
            {
                "message": "The calculation worker stopped before results were prepared.",
                "remediation": "Start a new calculation and download diagnostics if the problem continues.",
            }
        ],
    }


@dataclass(slots=True)
class _RunHandle:
    process: multiprocessing.Process
    cancel_event: Any


class _RunEventEmitter(PipelineObserver):
    """Persist ordered observer events and update the authoritative run row."""

    def __init__(self, engine: Any, run_id: str):
        self.run_id = run_id
        self.runs = RunRepository(engine)
        self.events = JobEventRepository(engine)
        self._lock = threading.RLock()
        self._stage_order = (
            "load_inputs",
            "prepare_geospatial_data",
            "assess_heat_resources",
            "build_optimization_context",
            "optimize_heat_grid",
            "write_outputs",
        )

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        payload = _json_safe(dict(data or {}))
        with self._lock:
            self._update_authoritative_state(event_type, payload)
            self._append(event_type, payload)

    def heartbeat(self) -> None:
        with self._lock:
            current = self.runs.get(self.run_id)
            if current.get("status") in {"completed", "failed", "cancelled"}:
                return
            self.runs.update_status(self.run_id, "running", heartbeat=True)
            self._append("heartbeat", {"status": "running"})

    def _append(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append_ordered(self.run_id, "run", event_type, data)

    def _update_authoritative_state(self, event_type: str, data: dict[str, Any]) -> None:
        if event_type == "pipeline.stage_started":
            stage = str(data.get("stage"))
            index = self._stage_order.index(stage) if stage in self._stage_order else 0
            self.runs.update_status(
                self.run_id,
                "running",
                stage=stage,
                progress={
                    "stage": stage,
                    "completed": index,
                    "total": len(self._stage_order),
                    "fraction": index / len(self._stage_order),
                },
                heartbeat=True,
            )
        elif event_type == "pipeline.stage_completed":
            stage = str(data.get("stage"))
            index = self._stage_order.index(stage) if stage in self._stage_order else 0
            self.runs.update_status(
                self.run_id,
                "running",
                stage=stage,
                progress={
                    "stage": stage,
                    "completed": index + 1,
                    "total": len(self._stage_order),
                    "fraction": (index + 1) / len(self._stage_order),
                },
                heartbeat=True,
            )
        elif event_type == "optimization.candidate_started":
            self.runs.update_status(
                self.run_id,
                "running",
                stage="optimize_heat_grid",
                candidate_progress={
                    "total_candidates": data.get("total_candidates"),
                    "current_candidate_id": data.get("candidate_id"),
                    "current_candidate_index": data.get("index"),
                    "completed_candidates": data.get("completed_candidates", 0),
                    "connected_candidates": data.get("connected_candidates", 0),
                    "rejected_candidates": data.get("rejected_candidates", 0),
                },
                heartbeat=True,
            )
        elif event_type == "optimization.candidate_completed":
            self.runs.update_status(
                self.run_id,
                "running",
                stage="optimize_heat_grid",
                candidate_progress={
                    "total_candidates": data.get("total_candidates"),
                    "current_candidate_id": data.get("candidate_id"),
                    "current_candidate_index": data.get("index"),
                    "completed_candidates": data.get("completed_candidates", 0),
                    "connected_candidates": data.get("connected_candidates", 0),
                    "rejected_candidates": data.get("rejected_candidates", 0),
                    "decision": data.get("decision"),
                },
                heartbeat=True,
            )
        elif event_type in {"pipeline.stage_failed", "optimization.candidate_failed"}:
            self.runs.update_status(
                self.run_id,
                "running",
                failure_details={"code": "PIPELINE_STAGE_FAILED", **data},
                heartbeat=True,
            )
        elif event_type == "job.warning":
            current = self.runs.get(self.run_id)
            warnings = list(current.get("warnings") or [])
            warnings.append(data)
            self.runs.update_status(self.run_id, "running", warnings=warnings, heartbeat=True)
        elif event_type == "heartbeat":
            self.runs.update_status(self.run_id, "running", heartbeat=True)
        # Status events are appended after the authoritative terminal update;
        # emitting one must never turn a completed/failed/cancelled run back
        # into ``running``.


class _HeartbeatThread:
    def __init__(self, emitter: _RunEventEmitter, interval: float = 5.0):
        self.emitter = emitter
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run,
            name=f"heartbeat-run-{emitter.run_id}",
            daemon=True,
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=max(1.0, self.interval + 1.0))

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval):
            try:
                self.emitter.heartbeat()
            except Exception:
                # The main worker will report the final failure.  A heartbeat
                # thread must never terminate optimization by itself.
                return


def run_run_worker(
    database_path: str | Path,
    project_root: str | Path,
    output_root: str | Path,
    run_id: str,
    scenario_id: str,
    scenario_revision_id: str,
    preview_id: str | None,
    configuration_snapshot: dict[str, Any],
    cancel_event: Any = None,
    *,
    output_label: str | None = None,
) -> None:
    """Execute one immutable run in a separate process.

    The function is intentionally a module-level target so multiprocessing can
    use it with the spawn start method on Windows as well as POSIX platforms.
    """

    settings = WebSettings(
        project_root=project_root,
        metadata_database_path=database_path,
        output_root=output_root,
    )
    engine = create_metadata_engine(settings)
    run_migrations(engine)
    runs = RunRepository(engine)
    emitter = _RunEventEmitter(engine, run_id)
    token = (
        CancellationToken.from_event(cancel_event)
        if cancel_event is not None
        else CancellationToken()
    )
    heartbeat = _HeartbeatThread(emitter)
    started_at = datetime.now(timezone.utc)
    safe_case = _safe_component(str(configuration_snapshot.get("scenario", {}).get("case", "run")))
    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    suffix = _safe_component(run_id[:8])
    label = _safe_component(output_label) if output_label else ""
    directory_name = "-".join(part for part in (timestamp, label, suffix) if part)
    output_path = Path(settings.output_root) / safe_case / directory_name
    log_path = output_path / "run.log"
    persisted_provenance = runs.get(run_id)
    configuration_version = persisted_provenance.get("configuration_version")
    bbox = persisted_provenance.get("bbox")
    data_snapshot = persisted_provenance.get("data_snapshot") or {}

    try:
        output_path.mkdir(parents=True, exist_ok=True)
        output_storage_key = output_path.relative_to(Path(settings.output_root)).as_posix()
        log_storage_key = log_path.relative_to(Path(settings.output_root)).as_posix()
        runs.set_output(
            run_id,
            output_storage_key=output_storage_key,
            log_storage_key=log_storage_key,
        )
        runs.set_process_identity(run_id, pid=os.getpid(), started_at=started_at)
        runs.update_status(
            run_id,
            "running",
            stage="starting",
            progress={"stage": "starting", "completed": 0, "total": 6, "fraction": 0.0},
            heartbeat=True,
        )
        emitter.emit("job.status_changed", {"status": "running", "pid": os.getpid()})
        heartbeat.start()
        token.raise_if_cancelled()

        config = load_config_from_document(
            configuration_snapshot,
            project_root=project_root,
            inherit_defaults=False,
        )
        with log_path.open("a", encoding="utf-8") as log_handle:
            with redirect_stdout(log_handle), redirect_stderr(log_handle):
                pipeline.run_pipeline(
                    config=config,
                    output_dir=output_path,
                    observer=emitter,
                    cancellation_token=token,
                )
        token.raise_if_cancelled()
        solver_name, solver_version = _solver_metadata()
        manifest_path = _write_manifest(
            output_path,
            run_id=run_id,
            scenario_id=scenario_id,
            scenario_revision_id=scenario_revision_id,
            preview_id=preview_id,
            configuration_snapshot=configuration_snapshot,
            configuration_version=configuration_version,
            bbox=bbox,
            data_snapshot=data_snapshot,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            solver_name=solver_name,
            solver_version=solver_version,
            status="completed",
            output_label=output_label,
        )
        storage_key = output_path.relative_to(Path(settings.output_root)).as_posix()
        log_key = log_path.relative_to(Path(settings.output_root)).as_posix()
        manifest_key = manifest_path.relative_to(Path(settings.output_root)).as_posix()
        runs.set_output(
            run_id,
            output_storage_key=storage_key,
            log_storage_key=log_key,
            manifest_storage_key=manifest_key,
            solver_name=solver_name,
            solver_version=solver_version,
        )
        _register_artifacts(engine, run_id, output_path, Path(settings.output_root), emitter)
        runs.update_status(
            run_id,
            "completed",
            stage="complete",
            progress={"stage": "complete", "completed": 6, "total": 6, "fraction": 1.0},
            heartbeat=True,
        )
        emitter.emit("job.status_changed", {"status": "completed"})
    except CancellationRequested as exc:
        try:
            manifest_path = _write_manifest(
                output_path,
                run_id=run_id,
                scenario_id=scenario_id,
                scenario_revision_id=scenario_revision_id,
                preview_id=preview_id,
                configuration_snapshot=configuration_snapshot,
                configuration_version=configuration_version,
                bbox=bbox,
                data_snapshot=data_snapshot,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                solver_name="unknown",
                solver_version="unknown",
                status="cancelled",
                output_label=output_label,
            )
            runs.set_output(
                run_id,
                output_storage_key=output_path.relative_to(Path(settings.output_root)).as_posix(),
                log_storage_key=log_path.relative_to(Path(settings.output_root)).as_posix(),
                manifest_storage_key=manifest_path.relative_to(
                    Path(settings.output_root)
                ).as_posix(),
            )
            _register_artifacts(engine, run_id, output_path, Path(settings.output_root), emitter)
            runs.update_status(
                run_id,
                "cancelled",
                stage="cancelled",
                failure_summary=str(exc),
                failure_details={"code": "CANCELLED"},
                heartbeat=True,
            )
            emitter.emit("job.status_changed", {"status": "cancelled"})
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001 - process boundary must persist failures
        message = f"{type(exc).__name__}: {exc}"
        failure_details = {
            **classify_run_failure(exc),
            "exception_type": type(exc).__name__,
        }
        # Persist the terminal state before attempting diagnostics. In
        # particular, a full output volume can make log/manifest writes fail
        # while the metadata database remains writable.
        try:
            runs.update_status(
                run_id,
                "failed",
                stage="failed",
                failure_summary=message,
                failure_details=failure_details,
                heartbeat=True,
            )
            emitter.emit(
                "job.failed",
                {
                    "code": failure_details["code"],
                    "message": message,
                    "traceback": traceback.format_exc(limit=12),
                },
            )
        except Exception:
            pass
        try:
            if output_path.parent.exists():
                output_path.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as log_handle:
                    log_handle.write("\n" + traceback.format_exc(limit=12))
            manifest_path = _write_manifest(
                output_path,
                run_id=run_id,
                scenario_id=scenario_id,
                scenario_revision_id=scenario_revision_id,
                preview_id=preview_id,
                configuration_snapshot=configuration_snapshot,
                configuration_version=configuration_version,
                bbox=bbox,
                data_snapshot=data_snapshot,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                solver_name="unknown",
                solver_version="unknown",
                status="failed",
                output_label=output_label,
            )
            runs.set_output(
                run_id,
                output_storage_key=output_path.relative_to(Path(settings.output_root)).as_posix(),
                log_storage_key=log_path.relative_to(Path(settings.output_root)).as_posix(),
                manifest_storage_key=manifest_path.relative_to(
                    Path(settings.output_root)
                ).as_posix(),
            )
            _register_artifacts(engine, run_id, output_path, Path(settings.output_root), emitter)
        except Exception:
            # Failure evidence is optional; the terminal run state above is
            # the recovery path when output storage itself is unavailable.
            pass
    finally:
        heartbeat.stop()
        try:
            runs.set_process_identity(run_id, pid=None)
        except Exception:
            pass
        engine.dispose()


def _register_artifacts(
    engine: Any,
    run_id: str,
    output_path: Path,
    output_root: Path,
    emitter: _RunEventEmitter,
) -> None:
    repository = ArtifactMetadataRepository(engine)
    media_types = {
        ".json": "application/json",
        ".geojson": "application/geo+json",
        ".png": "image/png",
        ".html": "text/html",
        ".log": "text/plain",
    }
    for path in sorted(item for item in output_path.rglob("*") if item.is_file()):
        relative = path.relative_to(output_root).as_posix()
        artifact = repository.create(
            run_id=run_id,
            display_name=path.name,
            description="Generated DH-COMPASS run artifact",
            media_type=media_types.get(path.suffix.lower(), "application/octet-stream"),
            storage_key=relative,
            status="available",
            byte_size=path.stat().st_size,
            checksum_sha256=_sha256(path),
        )
        emitter.emit(
            "artifact.created",
            {
                "artifact_id": artifact["id"],
                "display_name": path.name,
                "storage_key": relative,
            },
        )


def _write_manifest(
    output_path: Path,
    *,
    run_id: str,
    scenario_id: str,
    scenario_revision_id: str,
    preview_id: str | None,
    configuration_snapshot: dict[str, Any],
    configuration_version: str | None,
    bbox: list[float] | None,
    data_snapshot: dict[str, Any],
    started_at: datetime,
    finished_at: datetime,
    solver_name: str,
    solver_version: str,
    status: str,
    output_label: str | None,
) -> Path:
    files = sorted(
        {
            path.relative_to(output_path).as_posix(): _sha256(path)
            for path in output_path.rglob("*")
            if path.is_file()
        }.items()
    )
    manifest = {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "scenario_revision_id": scenario_revision_id,
        "preview_id": preview_id,
        "input_revision": preview_id,
        "result_schema_version": "1",
        "configuration_version": configuration_version,
        "bbox": _json_safe(bbox),
        "data_snapshot": _json_safe(data_snapshot),
        "configuration": _json_safe(configuration_snapshot),
        "application": {
            "version": __version__,
            "source_revision": os.environ.get("DH_COMPASS_SOURCE_REVISION"),
        },
        "solver": {"name": solver_name, "version": solver_version},
        "timestamps": {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
        },
        "status": status,
        "output_label": output_label,
        "artifacts": [{"path": path, "checksum_sha256": checksum} for path, checksum in files],
    }
    path = output_path / "run_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _solver_metadata() -> tuple[str, str]:
    try:
        import mip

        from dh_compass.optimization.model import selected_solver_backend

        backend = selected_solver_backend()
        if backend == mip.HIGHS:
            import mip.highs

            # Windows uses the highsbox DLL, which can differ from highspy's
            # Python-package version. Report the library that actually solves.
            return "HiGHS", mip.highs.ffi.string(mip.highs.highslib.Highs_version()).decode()
        if backend == mip.GRB:
            return "Gurobi (python-mip)", str(getattr(mip, "__version__", "unknown"))
        return "python-mip", str(getattr(mip, "__version__", "unknown"))
    except Exception:
        return "unknown", "unknown"


def _safe_component(value: str | None) -> str:
    if not value:
        return "run"
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    return (cleaned or "run")[:120]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RunJobManager:
    """Schedule isolated run workers with a configurable concurrency limit."""

    def __init__(self, settings: WebSettings, metadata_engine: Any | None = None):
        self.settings = settings
        self.metadata_engine = metadata_engine
        self._jobs: dict[str, _RunHandle] = {}
        self._lock = threading.RLock()

    def attach_metadata_engine(self, engine: Any) -> None:
        """Use the lifespan-owned engine for request-process metadata access."""

        self.metadata_engine = engine

    @contextmanager
    def _metadata(self):
        if self.metadata_engine is not None:
            yield self.metadata_engine
            return
        engine = create_metadata_engine(self.settings)
        try:
            run_migrations(engine)
            yield engine
        finally:
            engine.dispose()

    def start(
        self,
        *,
        run_id: str,
        scenario_id: str,
        scenario_revision_id: str,
        preview_id: str | None,
        configuration_snapshot: dict[str, Any],
        output_label: str | None = None,
        worker_target: Callable[..., Any] = run_run_worker,
    ) -> bool:
        """Queue or launch a run, returning whether a process was started."""

        with self._lock:
            if run_id in self._jobs:
                raise RunJobProcessError(f"Run {run_id} is already running.")
            if len(self._jobs) >= self.settings.worker_concurrency:
                return False
            self._launch(
                run_id=run_id,
                scenario_id=scenario_id,
                scenario_revision_id=scenario_revision_id,
                preview_id=preview_id,
                configuration_snapshot=configuration_snapshot,
                output_label=output_label,
                worker_target=worker_target,
            )
            return True

    def schedule_queued(self, *, worker_target: Callable[..., Any] = run_run_worker) -> None:
        """Start persisted queued jobs until the solver concurrency is full."""

        with self._lock:
            available = self.settings.worker_concurrency - len(self._jobs)
            if available <= 0:
                return
            with self._metadata() as engine:
                records = [
                    record
                    for record in RunRepository(engine).list_by_status(("queued",))
                    if record.get("execution_mode") != "calculation"
                ]
            for record in records[:available]:
                try:
                    self._launch(
                        run_id=record["id"],
                        scenario_id=record["scenario_id"],
                        scenario_revision_id=record["scenario_revision_id"],
                        preview_id=record.get("preview_id"),
                        configuration_snapshot=record.get("configuration_snapshot") or {},
                        output_label=record.get("output_label"),
                        worker_target=worker_target,
                    )
                except RunJobProcessError:
                    # The launch method persists an error for an individual
                    # run.  Other queued runs remain eligible for scheduling.
                    continue

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            handle = self._jobs.get(run_id)
            with self._metadata() as engine:
                repository = RunRepository(engine)
                current = repository.get(run_id)
                if current["status"] in {"completed", "failed", "cancelled"}:
                    return True
                if handle is None:
                    if current["status"] == "queued":
                        repository.update_status(
                            run_id,
                            "cancelled",
                            stage="cancelled",
                            failure_summary="Cancellation was requested before the worker started.",
                            failure_details={"code": "CANCELLED_BEFORE_START"},
                        )
                        _append_run_event(
                            engine,
                            run_id,
                            "job.status_changed",
                            {"status": "cancelled"},
                        )
                        return True
                    return False
                handle.cancel_event.set()
                repository.update_status(run_id, "cancellation_requested", heartbeat=True)
                _append_run_event(
                    engine,
                    run_id,
                    "job.status_changed",
                    {"status": "cancellation_requested"},
                )
                return True

    def is_running(self, run_id: str) -> bool:
        with self._lock:
            handle = self._jobs.get(run_id)
            return bool(handle and handle.process.is_alive())

    def recover(self, *, worker_target: Callable[..., Any] = run_run_worker) -> None:
        """Reconcile workers from an API process that no longer exists."""

        with self._metadata() as engine:
            repository = RunRepository(engine)
            interrupted = repository.reconcile_interrupted(
                "The API restarted while this run worker was active."
            )
            for record in interrupted:
                _append_run_event(
                    engine,
                    record["id"],
                    "job.failed",
                    {
                        "code": "WORKER_INTERRUPTED",
                        "message": record["failure_summary"],
                    },
                )
        self.schedule_queued(worker_target=worker_target)

    def _launch(
        self,
        *,
        run_id: str,
        scenario_id: str,
        scenario_revision_id: str,
        preview_id: str | None,
        configuration_snapshot: dict[str, Any],
        output_label: str | None = None,
        worker_target: Callable[..., Any],
    ) -> None:
        context = multiprocessing.get_context("spawn")
        cancel_event = context.Event()
        kwargs = {"output_label": output_label} if output_label is not None else {}
        process = context.Process(
            target=worker_target,
            args=(
                self.settings.metadata_database_path,
                self.settings.project_root,
                self.settings.output_root,
                run_id,
                scenario_id,
                scenario_revision_id,
                preview_id,
                dict(configuration_snapshot),
                cancel_event,
            ),
            kwargs=kwargs,
            name=f"dh-compass-run-{run_id}",
            daemon=True,
        )
        try:
            process.start()
        except Exception as exc:  # noqa: BLE001 - process boundary includes pickling errors
            self._mark_launch_failed(run_id, str(exc))
            raise RunJobProcessError("The run worker could not be started.") from exc
        self._jobs[run_id] = _RunHandle(process=process, cancel_event=cancel_event)
        with self._metadata() as engine:
            RunRepository(engine).set_process_identity(run_id, pid=process.pid)
            _append_run_event(
                engine,
                run_id,
                "worker.started",
                {"status": "running", "pid": process.pid},
            )
        watcher = threading.Thread(
            target=self._watch,
            args=(run_id, process, worker_target),
            name=f"watch-run-{run_id}",
            daemon=True,
        )
        watcher.start()

    def _mark_launch_failed(self, run_id: str, message: str) -> None:
        with self._metadata() as engine:
            RunRepository(engine).update_status(
                run_id,
                "failed",
                stage="failed",
                failure_summary=f"Run worker unavailable: {message}",
                failure_details={
                    "code": "RUN_WORKER_UNAVAILABLE",
                    "issues": [
                        {
                            "message": "A calculation worker could not be started.",
                            "remediation": "Check the worker service and solver installation, then start a new calculation.",
                        }
                    ],
                },
            )
            _append_run_event(
                engine,
                run_id,
                "job.failed",
                {"code": "RUN_WORKER_UNAVAILABLE", "message": message},
            )

    def _watch(
        self,
        run_id: str,
        process: multiprocessing.Process,
        worker_target: Callable[..., Any],
    ) -> None:
        process.join()
        with self._lock:
            self._jobs.pop(run_id, None)
        try:
            with self._metadata() as engine:
                repository = RunRepository(engine)
                current = repository.get(run_id)
                if current["status"] in {"queued", "running", "cancellation_requested"}:
                    if current["status"] == "cancellation_requested":
                        status = "cancelled"
                        message = "The run was cancelled before the worker reported completion."
                        event_type = "job.status_changed"
                    else:
                        status = "failed"
                        message = (
                            "The run worker exited without reporting a final state"
                            if process.exitcode == 0
                            else f"The run worker stopped unexpectedly (exit code {process.exitcode})."
                        )
                        event_type = "job.failed"
                    repository.update_status(
                        run_id,
                        status,
                        stage=status,
                        failure_summary=message,
                        failure_details={
                            "code": "WORKER_EXITED",
                            "issues": [
                                {
                                    "message": "The calculation worker exited before reporting a final result.",
                                    "remediation": "Start a new calculation and download diagnostics if the problem continues.",
                                }
                            ],
                        },
                    )
                    _append_run_event(
                        engine,
                        run_id,
                        event_type,
                        {"status": status, "message": message},
                    )
                repository.set_process_identity(run_id, pid=None)
        except Exception:
            # API shutdown or a deleted record must not crash the watcher.
            pass
        self.schedule_queued(worker_target=worker_target)


def _append_run_event(
    engine: Any,
    run_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    events = JobEventRepository(engine)
    return events.append_ordered(run_id, "run", event_type, data or {})


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


__all__ = [
    "classify_run_failure",
    "RunCancelled",
    "RunJobProcessError",
    "run_run_worker",
]
