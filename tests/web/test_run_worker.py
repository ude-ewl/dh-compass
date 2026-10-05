from __future__ import annotations

import errno
from importlib.util import find_spec
from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.skipif(
    any(find_spec(name) is None for name in ("fastapi", "pydantic", "sqlalchemy")),
    reason="web dependencies are not installed",
)


def test_solver_metadata_reports_actual_highs_library(monkeypatch):
    import mip.highs
    from mip import HIGHS, Model

    from dh_compass.optimization import model
    from dh_compass.web.jobs.run import _solver_metadata

    problem = Model(solver_name=HIGHS)
    monkeypatch.setattr(model, "_selected_backend", HIGHS)
    name, version = _solver_metadata()
    assert name == "HiGHS"
    assert version == mip.highs.ffi.string(mip.highs.highslib.Highs_version()).decode()
    assert problem.solver_name == HIGHS


def _worker_fixture(tmp_path: Path):
    from dh_compass.web.persistence.database import create_metadata_engine
    from dh_compass.web.persistence.migrations import run_migrations
    from dh_compass.web.persistence.repositories import (
        ProjectRepository,
        RunRepository,
        ScenarioRepository,
    )
    from dh_compass.web.services.configuration import ConfigurationAdapter
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
        output_root=tmp_path / "outputs",
    )
    engine = create_metadata_engine(settings)
    run_migrations(engine)
    project = ProjectRepository(engine).create("Worker test project")
    scenario = ScenarioRepository(engine, ConfigurationAdapter(tmp_path)).create(
        project["id"], "Worker test scenario"
    )
    run = RunRepository(engine).create(
        scenario["id"],
        scenario["current_revision_id"],
        "Worker test run",
        configuration_snapshot={"scenario": {"case": "worker-test"}},
    )
    return settings, engine, run


def test_run_worker_persists_completed_state_and_manifest(tmp_path: Path) -> None:
    from dh_compass.web.jobs.run import run_run_worker
    from dh_compass.web.persistence.repositories import (
        ArtifactMetadataRepository,
        JobEventRepository,
        RunRepository,
    )

    settings, engine, run = _worker_fixture(tmp_path)
    try:
        with (
            patch(
                "dh_compass.web.jobs.run.load_config_from_document",
                return_value=object(),
            ),
            patch("dh_compass.web.jobs.run.pipeline.run_pipeline"),
            patch(
                "dh_compass.web.jobs.run._solver_metadata",
                return_value=("test-solver", "1.2"),
            ),
        ):
            run_run_worker(
                settings.metadata_database_path,
                settings.project_root,
                settings.output_root,
                run["id"],
                run["scenario_id"],
                run["scenario_revision_id"],
                None,
                run["configuration_snapshot"],
            )

        completed = RunRepository(engine).get(run["id"])
        assert completed["status"] == "completed"
        assert completed["solver"] == {"name": "test-solver", "version": "1.2"}
        assert completed["manifest_storage_key"]

        artifacts = ArtifactMetadataRepository(engine).list_for_run(run["id"])
        names = {artifact["display_name"] for artifact in artifacts}
        assert {"run.log", "run_manifest.json"}.issubset(names)
        assert all(artifact["status"] == "available" for artifact in artifacts)

        events = JobEventRepository(engine).list(run["id"], "run")
        assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
        assert events[-1]["event_type"] == "job.status_changed"
        assert events[-1]["data"]["status"] == "completed"
    finally:
        engine.dispose()


def test_run_worker_persists_failure_diagnostics(tmp_path: Path) -> None:
    from dh_compass.web.jobs.run import run_run_worker
    from dh_compass.web.persistence.repositories import (
        ArtifactMetadataRepository,
        RunRepository,
    )

    settings, engine, run = _worker_fixture(tmp_path)
    try:
        with (
            patch(
                "dh_compass.web.jobs.run.load_config_from_document",
                return_value=object(),
            ),
            patch(
                "dh_compass.web.jobs.run.pipeline.run_pipeline",
                side_effect=RuntimeError("fixture solver failed"),
            ),
        ):
            run_run_worker(
                settings.metadata_database_path,
                settings.project_root,
                settings.output_root,
                run["id"],
                run["scenario_id"],
                run["scenario_revision_id"],
                None,
                run["configuration_snapshot"],
            )

        failed = RunRepository(engine).get(run["id"])
        assert failed["status"] == "failed"
        assert "fixture solver failed" in failed["failure_summary"]
        assert failed["failure_details"]["code"] == "RUN_WORKER_FAILED"

        artifacts = ArtifactMetadataRepository(engine).list_for_run(run["id"])
        log = next(artifact for artifact in artifacts if artifact["display_name"] == "run.log")
        log_path = Path(settings.output_root) / str(log["storage_key"])
        assert "RuntimeError: fixture solver failed" in log_path.read_text(encoding="utf-8")
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (OSError(errno.ENOSPC, "No space left on device"), "OUTPUT_STORAGE_FULL"),
        (ModuleNotFoundError("No module named 'mip'"), "SOLVER_UNAVAILABLE"),
    ],
)
def test_run_worker_classifies_actionable_failures(
    tmp_path: Path, error: Exception, expected_code: str
) -> None:
    from dh_compass.web.jobs.run import run_run_worker
    from dh_compass.web.persistence.repositories import RunRepository

    settings, engine, run = _worker_fixture(tmp_path)
    try:
        with (
            patch(
                "dh_compass.web.jobs.run.load_config_from_document",
                return_value=object(),
            ),
            patch(
                "dh_compass.web.jobs.run.pipeline.run_pipeline",
                side_effect=error,
            ),
        ):
            run_run_worker(
                settings.metadata_database_path,
                settings.project_root,
                settings.output_root,
                run["id"],
                run["scenario_id"],
                run["scenario_revision_id"],
                None,
                run["configuration_snapshot"],
            )

        failed = RunRepository(engine).get(run["id"])
        assert failed["status"] == "failed"
        assert failed["failure_details"]["code"] == expected_code
        assert failed["failure_details"]["issues"][0]["remediation"]
    finally:
        engine.dispose()


def test_run_worker_honours_cooperative_cancellation(tmp_path: Path) -> None:
    from dh_compass.web.jobs.run import run_run_worker
    from dh_compass.web.persistence.repositories import (
        ArtifactMetadataRepository,
        RunRepository,
    )

    settings, engine, run = _worker_fixture(tmp_path)
    cancel_event = Event()
    cancel_event.set()
    try:
        with patch(
            "dh_compass.web.jobs.run.load_config_from_document",
            side_effect=AssertionError("cancelled run must not load configuration"),
        ):
            run_run_worker(
                settings.metadata_database_path,
                settings.project_root,
                settings.output_root,
                run["id"],
                run["scenario_id"],
                run["scenario_revision_id"],
                None,
                run["configuration_snapshot"],
                cancel_event,
            )

        cancelled = RunRepository(engine).get(run["id"])
        assert cancelled["status"] == "cancelled"
        assert cancelled["failure_details"]["code"] == "CANCELLED"
        names = {
            artifact["display_name"]
            for artifact in ArtifactMetadataRepository(engine).list_for_run(run["id"])
        }
        assert "run_manifest.json" in names
    finally:
        engine.dispose()
