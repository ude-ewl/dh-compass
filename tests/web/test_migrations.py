from importlib.util import find_spec
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(find_spec("sqlalchemy") is None, reason="web dependencies are not installed")


def test_metadata_migrations_are_repeatable(tmp_path: Path) -> None:
    from dh_compass.web.persistence.database import create_metadata_engine
    from dh_compass.web.persistence.migrations import current_version, run_migrations
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
    )
    engine = create_metadata_engine(settings)
    try:
        assert current_version(engine) == 0
        assert run_migrations(engine) == 2
        assert run_migrations(engine) == 2
        with engine.connect() as connection:
            tables = {
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        assert {
            "schema_migrations",
            "web_metadata",
            "projects",
            "scenarios",
            "scenario_revisions",
            "previews",
            "runs",
            "job_events",
            "artifact_metadata",
            "study_areas",
            "dataset_states",
        }.issubset(tables)
    finally:
        engine.dispose()


def test_metadata_migrations_upgrade_an_existing_version_one_database(tmp_path: Path) -> None:
    from sqlalchemy import text

    from dh_compass.web.persistence.database import create_metadata_engine
    from dh_compass.web.persistence.migrations import MIGRATIONS, run_migrations
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
    )
    engine = create_metadata_engine(settings)
    try:
        # Simulate the released Milestone 2 schema: version 1 exists, but the
        # run-execution columns and readiness helper tables do not.
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
            for statement in MIGRATIONS[0].statements:
                connection.exec_driver_sql(statement)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations(version, name, applied_at) "
                    "VALUES (1, :name, '2024-01-01T00:00:00+00:00')"
                ),
                {"name": MIGRATIONS[0].name},
            )

        with engine.connect() as connection:
            columns = {
                row[1]
                for row in connection.exec_driver_sql("PRAGMA table_info(runs)")
            }
        assert "configuration_snapshot_json" not in columns

        assert run_migrations(engine) == 2
        with engine.connect() as connection:
            columns = {
                row[1]
                for row in connection.exec_driver_sql("PRAGMA table_info(runs)")
            }
            tables = {
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        assert "configuration_snapshot_json" in columns
        assert {"study_areas", "dataset_states"}.issubset(tables)
    finally:
        engine.dispose()


def test_metadata_migrations_reconcile_the_intermediate_run_schema(tmp_path: Path) -> None:
    from dh_compass.web.persistence.database import create_metadata_engine
    from dh_compass.web.persistence.migrations import MIGRATIONS, run_migrations
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
    )
    engine = create_metadata_engine(settings)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
            for statement in MIGRATIONS[0].statements:
                connection.exec_driver_sql(statement)
            # This was the transient version-1 shape used by the previous
            # implementation. It must not make the version-2 ALTERs fail.
            for statement in MIGRATIONS[1].statements:
                if statement.lstrip().upper().startswith("ALTER TABLE"):
                    connection.exec_driver_sql(statement)
            connection.exec_driver_sql(
                "INSERT INTO schema_migrations(version, name, applied_at) "
                "VALUES (1, 'projects_scenarios_jobs_and_run_execution', '2024-01-01')"
            )

        assert run_migrations(engine) == 2
    finally:
        engine.dispose()
