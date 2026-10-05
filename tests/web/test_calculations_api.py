from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.skipif(
    any(find_spec(name) is None for name in ("fastapi", "pydantic", "sqlalchemy")),
    reason="web dependencies are not installed",
)


def test_one_command_calculation_is_idempotent_and_records_defaults(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.persistence.database import create_metadata_engine
    from dh_compass.web.persistence.migrations import run_migrations
    from dh_compass.web.persistence.repositories import (
        ProjectRepository,
        RunRepository,
        ScenarioRepository,
        StudyAreaRepository,
    )
    from dh_compass.web.services.configuration import ConfigurationAdapter
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
        output_root=tmp_path / "outputs",
    )
    bbox = [7.1, 51.2, 7.2, 51.3]
    with patch(
        "dh_compass.web.api.calculations.CalculationJobManager.start",
        return_value=True,
    ) as start:
        with TestClient(create_app(settings)) as client:
            first = client.post(
                "/api/v1/calculations",
                json={"bbox": bbox},
                headers={"Idempotency-Key": "calculation-1"},
            )
            assert first.status_code == 202
            accepted = first.json()
            assert accepted["status"] == "queued"
            assert accepted["bbox"] == bbox
            assert accepted["configuration_version"] == "default-v1"
            assert accepted["idempotency_replayed"] is False

            second = client.post(
                "/api/v1/calculations",
                json={"bbox": bbox},
                headers={"Idempotency-Key": "calculation-1"},
            )
            assert second.status_code == 202
            assert second.json()["run_id"] == accepted["run_id"]
            assert second.json()["idempotency_replayed"] is True

            different = client.post(
                "/api/v1/calculations",
                json={"bbox": [7.1, 51.2, 7.3, 51.3]},
                headers={"Idempotency-Key": "calculation-1"},
            )
            assert different.status_code == 409
            assert different.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

            run_response = client.get(accepted["status_url"])
            assert run_response.status_code == 200
            run = run_response.json()
            assert run["configuration_version"] == "default-v1"
            assert run["bbox"] == bbox
            assert run["configuration_snapshot"]["scenario"]["bbox"] == bbox

        assert start.call_count == 1

    engine = create_metadata_engine(settings)
    try:
        run_migrations(engine)
        run = RunRepository(engine).get(accepted["run_id"])
        assert run["execution_mode"] == "calculation"
        scenario = ScenarioRepository(
            engine, ConfigurationAdapter(tmp_path)
        ).get(run["scenario_id"])
        assert ProjectRepository(engine).get(scenario["project_id"])["scenario_count"] == 1
        assert StudyAreaRepository(engine).get(scenario["id"])["execution_bbox"] == bbox
    finally:
        engine.dispose()


def test_concurrent_idempotent_submissions_share_one_run(tmp_path: Path) -> None:
    from dh_compass.web.persistence.database import create_metadata_engine
    from dh_compass.web.persistence.migrations import run_migrations
    from dh_compass.web.services.calculation import CalculationSubmissionService
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
    )
    engine = create_metadata_engine(settings)
    try:
        run_migrations(engine)

        def submit():
            return CalculationSubmissionService(engine, str(tmp_path)).submit(
                [7.1, 51.2, 7.2, 51.3],
                idempotency_key="concurrent-calculation",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            submissions = list(executor.map(lambda _: submit(), range(2)))

        assert {submission.run["id"] for submission in submissions} == {
            submissions[0].run["id"]
        }
        assert sorted(submission.idempotency_replayed for submission in submissions) == [False, True]
    finally:
        engine.dispose()


def test_bbox_rejection_happens_before_a_run_is_created(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.persistence.database import create_metadata_engine
    from dh_compass.web.persistence.migrations import run_migrations
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/calculations",
            json={"bbox": [7.1, 51.2, 7.10001, 51.20001]},
            headers={"Idempotency-Key": "invalid-1"},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "BBOX_TOO_SMALL"

    engine = create_metadata_engine(settings)
    try:
        run_migrations(engine)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM runs").scalar_one() == 0
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM projects").scalar_one() == 0
    finally:
        engine.dispose()


def test_non_numeric_bbox_uses_the_calculation_contract_error(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/calculations",
            json={"bbox": ["7.1", 51.2, 7.2, 51.3]},
            headers={"Idempotency-Key": "invalid-coordinate"},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "BBOX_COORDINATES_INVALID"


def test_data_preflight_failure_is_persisted_on_the_accepted_run(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
        output_root=tmp_path / "outputs",
    )
    with TestClient(create_app(settings)) as client:
        # This test exercises persisted validation failures without network I/O.
        client.app.state.cache_refreshers = {}
        accepted = client.post(
            "/api/v1/calculations",
            json={"bbox": [7.1, 51.2, 7.2, 51.3]},
            headers={"Idempotency-Key": "missing-data"},
        )
        assert accepted.status_code == 202

        run = None
        for _ in range(50):
            response = client.get(accepted.json()["status_url"])
            assert response.status_code == 200
            run = response.json()
            if run["status"] == "failed":
                break
            time.sleep(0.05)

    assert run is not None
    assert run["status"] == "failed"
    assert run["stage"] == "checking_input_data"
    assert run["failure_details"]["code"] == "DATA_NOT_READY"
    assert run["data_snapshot"]["datasets"]


def test_submission_creation_is_atomic_with_its_idempotency_key(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.persistence.database import create_metadata_engine
    from dh_compass.web.persistence.migrations import run_migrations
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
        output_root=tmp_path / "outputs",
    )
    engine = create_metadata_engine(settings)
    try:
        run_migrations(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TRIGGER reject_calculation_scenario
                BEFORE INSERT ON scenarios
                WHEN NEW.name = 'Study area calculation'
                BEGIN
                    SELECT RAISE(ABORT, 'injected scenario failure');
                END
                """
            )

        with patch(
            "dh_compass.web.api.calculations.CalculationJobManager.start",
            return_value=True,
        ):
            with TestClient(create_app(settings), raise_server_exceptions=False) as client:
                first = client.post(
                    "/api/v1/calculations",
                    json={"bbox": [7.1, 51.2, 7.2, 51.3]},
                    headers={"Idempotency-Key": "atomic-submission"},
                )
                assert first.status_code == 500

                with engine.connect() as connection:
                    assert connection.exec_driver_sql(
                        "SELECT COUNT(*) FROM calculation_requests"
                    ).scalar_one() == 0
                    assert connection.exec_driver_sql("SELECT COUNT(*) FROM projects").scalar_one() == 0
                    assert connection.exec_driver_sql("SELECT COUNT(*) FROM runs").scalar_one() == 0

                with engine.begin() as connection:
                    connection.exec_driver_sql("DROP TRIGGER reject_calculation_scenario")

                retry = client.post(
                    "/api/v1/calculations",
                    json={"bbox": [7.1, 51.2, 7.2, 51.3]},
                    headers={"Idempotency-Key": "atomic-submission"},
                )
                assert retry.status_code == 202
    finally:
        engine.dispose()
