"""Small, explicit SQLite migration registry.

The application never calls ``metadata.create_all`` or creates feature tables
implicitly while handling a request.  Schema changes are ordered migrations
and are applied by the application lifespan (or by an operator-facing command
in a later milestone).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import Engine, text

from .identifiers import utc_now


class MigrationError(RuntimeError):
    """Raised when a metadata database cannot be brought to a known version."""


@dataclass(frozen=True, slots=True)
class Migration:
    """One ordered database migration."""

    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="projects_scenarios_and_jobs",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS web_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,

            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS scenarios (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
                current_revision_id TEXT,
                readiness_state TEXT NOT NULL DEFAULT 'incomplete',
                preview_id TEXT,
                preview_stale_reason TEXT,
                run_required INTEGER NOT NULL DEFAULT 0 CHECK (run_required IN (0, 1)),
                area_summary_json TEXT NOT NULL DEFAULT '{}',
                effective_lhd_threshold REAL,
                expert_override_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS scenario_revisions (
                id TEXT PRIMARY KEY,
                scenario_id TEXT NOT NULL,
                parent_revision_id TEXT,
                revision_number INTEGER NOT NULL,
                document_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_revision_id) REFERENCES scenario_revisions(id),
                UNIQUE (scenario_id, revision_number)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS previews (
                id TEXT PRIMARY KEY,
                scenario_id TEXT NOT NULL,
                scenario_revision_id TEXT NOT NULL,
                status TEXT NOT NULL,
                stale_reason TEXT,
                linear_heat_density_threshold REAL,
                summary_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE,
                FOREIGN KEY (scenario_revision_id) REFERENCES scenario_revisions(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                scenario_id TEXT NOT NULL,
                scenario_revision_id TEXT NOT NULL,
                preview_id TEXT,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                failure_summary TEXT,
                warnings_json TEXT NOT NULL DEFAULT '[]',
                started_at TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE,
                FOREIGN KEY (scenario_revision_id) REFERENCES scenario_revisions(id),
                FOREIGN KEY (preview_id) REFERENCES previews(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS job_events (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                job_kind TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                data_json TEXT NOT NULL DEFAULT '{}',
                occurred_at TEXT NOT NULL,
                UNIQUE (job_kind, job_id, sequence)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS artifact_metadata (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                preview_id TEXT,
                display_name TEXT NOT NULL,
                description TEXT,
                media_type TEXT NOT NULL,
                byte_size INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                checksum_sha256 TEXT,
                storage_key TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
                FOREIGN KEY (preview_id) REFERENCES previews(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_scenarios_project_id ON scenarios(project_id)",
            "CREATE INDEX IF NOT EXISTS ix_scenario_revisions_scenario_id ON scenario_revisions(scenario_id)",
            "CREATE INDEX IF NOT EXISTS ix_previews_scenario_id ON previews(scenario_id)",
            "CREATE INDEX IF NOT EXISTS ix_runs_scenario_id ON runs(scenario_id)",
            "CREATE INDEX IF NOT EXISTS ix_runs_status ON runs(status)",
            "CREATE INDEX IF NOT EXISTS ix_job_events_job ON job_events(job_kind, job_id, sequence)",
            "CREATE INDEX IF NOT EXISTS ix_artifact_metadata_run_id ON artifact_metadata(run_id)",
        ),
    ),
    Migration(
        version=2,
        name="run_execution_and_readiness_support",
        statements=(
            "ALTER TABLE runs ADD COLUMN current_stage TEXT",
            "ALTER TABLE runs ADD COLUMN progress_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE runs ADD COLUMN candidate_progress_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE runs ADD COLUMN configuration_snapshot_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE runs ADD COLUMN output_storage_key TEXT",
            "ALTER TABLE runs ADD COLUMN log_storage_key TEXT",
            "ALTER TABLE runs ADD COLUMN manifest_storage_key TEXT",
            "ALTER TABLE runs ADD COLUMN process_pid INTEGER",
            "ALTER TABLE runs ADD COLUMN process_started_at TEXT",
            "ALTER TABLE runs ADD COLUMN heartbeat_at TEXT",
            "ALTER TABLE runs ADD COLUMN application_version TEXT",
            "ALTER TABLE runs ADD COLUMN solver_name TEXT",
            "ALTER TABLE runs ADD COLUMN solver_version TEXT",
            "ALTER TABLE runs ADD COLUMN idempotency_key TEXT",
            "ALTER TABLE runs ADD COLUMN output_label TEXT",
            "ALTER TABLE runs ADD COLUMN failure_details_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE runs ADD COLUMN configuration_version TEXT",
            "ALTER TABLE runs ADD COLUMN bbox_json TEXT",
            "ALTER TABLE runs ADD COLUMN data_snapshot_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE runs ADD COLUMN execution_mode TEXT NOT NULL DEFAULT 'standard'",
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_runs_idempotency ON runs(scenario_id, idempotency_key) WHERE idempotency_key IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS ix_runs_heartbeat ON runs(status, heartbeat_at)",
            "CREATE INDEX IF NOT EXISTS ix_runs_status ON runs(status)",
            "CREATE INDEX IF NOT EXISTS ix_job_events_job ON job_events(job_kind, job_id, sequence)",
            "CREATE INDEX IF NOT EXISTS ix_artifact_metadata_run_id ON artifact_metadata(run_id)",
            """
            CREATE TABLE IF NOT EXISTS calculation_requests (
                idempotency_key TEXT PRIMARY KEY,
                bbox_json TEXT NOT NULL,
                run_id TEXT,
                status TEXT NOT NULL DEFAULT 'in_progress',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE SET NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_calculation_requests_run_id ON calculation_requests(run_id)",
            """
            CREATE TABLE IF NOT EXISTS study_areas (
                scenario_id TEXT PRIMARY KEY,
                display_geometry_json TEXT,
                execution_bbox_json TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'bbox',
                imported_filename TEXT,
                crs TEXT,
                validation_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL,
                FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS dataset_states (
                scenario_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (scenario_id, dataset_id),
                FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_study_areas_scenario_id ON study_areas(scenario_id)",
            "CREATE INDEX IF NOT EXISTS ix_dataset_states_scenario_id ON dataset_states(scenario_id)",
            # Milestone 7 metadata is kept in the same versioned SQLite store.
            # The tables are additive and deliberately do not contain result
            # data; completed runs remain the source of truth for artifacts.
            """
            CREATE TABLE IF NOT EXISTS comparisons (
                id TEXT PRIMARY KEY,
                run_ids_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS export_jobs (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                display_name TEXT NOT NULL,
                media_type TEXT NOT NULL,
                storage_key TEXT,
                byte_size INTEGER,
                checksum_sha256 TEXT,
                error TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_records (
                id TEXT PRIMARY KEY,
                actor TEXT,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT,
                data_json TEXT NOT NULL DEFAULT '{}',
                occurred_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_comparisons_updated_at ON comparisons(updated_at)",
            "CREATE INDEX IF NOT EXISTS ix_export_jobs_run_id ON export_jobs(run_id)",
            "CREATE INDEX IF NOT EXISTS ix_export_jobs_status ON export_jobs(status)",
            "CREATE INDEX IF NOT EXISTS ix_audit_records_resource ON audit_records(resource_type, resource_id, occurred_at)",
        ),
    ),
)


_ADD_COLUMN = re.compile(
    r"^\s*ALTER\s+TABLE\s+(?P<table>[A-Za-z_][A-Za-z0-9_]*)"
    r"\s+ADD\s+COLUMN\s+(?P<column>[A-Za-z_][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
)


def _execute_migration_statements(connection, statements: tuple[str, ...]) -> None:
    """Execute migration SQL while tolerating an interrupted column upgrade.

    SQLite has no ``ADD COLUMN IF NOT EXISTS``. A development build briefly
    shipped run-execution columns under version 1, so a deployment can
    legitimately have those columns before version 2 is recorded. Checking
    only the controlled ``ALTER TABLE`` form keeps normal migrations explicit
    while making that upgrade path safe and repeatable.
    """

    for statement in statements:
        match = _ADD_COLUMN.match(statement)
        if match:
            table = match.group("table")
            column = match.group("column")
            columns = {
                str(row[1])
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            if column in columns:
                continue
        connection.exec_driver_sql(statement)


def _ensure_migration_table(engine: Engine) -> None:
    # This bookkeeping table is the migration mechanism itself.  Application
    # tables are introduced only by entries in MIGRATIONS.
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )


def current_version(engine: Engine) -> int:
    """Return the highest applied migration version, or zero for a new DB."""

    _ensure_migration_table(engine)
    with engine.connect() as connection:
        value = connection.execute(
            text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
        ).scalar_one()
    return int(value)


def run_migrations(engine: Engine) -> int:
    """Apply all known migrations and return the resulting schema version."""

    _ensure_migration_table(engine)
    known_versions = {migration.version for migration in MIGRATIONS}
    if len(known_versions) != len(MIGRATIONS):
        raise MigrationError("migration versions must be unique")

    with engine.connect() as connection:
        applied_rows = connection.execute(
            text("SELECT version, name FROM schema_migrations ORDER BY version")
        ).mappings().all()
    applied = {int(row["version"]) for row in applied_rows}
    applied_names = {int(row["version"]): str(row["name"]) for row in applied_rows}

    unknown = applied - known_versions
    if unknown:
        versions = ", ".join(str(version) for version in sorted(unknown))
        raise MigrationError(f"database contains unknown migration version(s): {versions}")

    expected = 0
    for migration in sorted(MIGRATIONS, key=lambda item: item.version):
        if migration.version <= expected:
            continue
        if migration.version != expected + 1:
            raise MigrationError(
                f"migration sequence skips version {expected + 1} before {migration.version}"
            )
        expected = migration.version
        if migration.version in applied:
            # A name mismatch indicates a database created by an older or
            # development build. Replay its idempotent compatibility SQL and
            # record the canonical migration name before continuing.
            if applied_names.get(migration.version) == migration.name:
                if migration.version not in {1, 2}:
                    continue
                # Very early development databases recorded version 1 after
                # creating only the bookkeeping table. Re-run the base
                # migration if its domain tables are absent.  Version 2 also
                # gained additive Milestone 7 tables after the first release;
                # replay the idempotent statements when one of those tables is
                # missing without changing the public schema version.
                required_tables = {
                    1: {"runs"},
                    2: {"comparisons", "export_jobs", "audit_records", "calculation_requests"},
                }[migration.version]
                with engine.connect() as connection:
                    existing_tables = {
                        str(row[0])
                        for row in connection.execute(
                            text(
                                "SELECT name FROM sqlite_master "
                                "WHERE type='table' AND name IN "
                                "('runs', 'comparisons', 'export_jobs', 'audit_records', "
                                "'calculation_requests')"
                            )
                        )
                    }
                if required_tables.issubset(existing_tables):
                    continue
            with engine.begin() as connection:
                _execute_migration_statements(connection, migration.statements)
                connection.execute(
                    text(
                        "UPDATE schema_migrations SET name=:name, applied_at=:applied_at "
                        "WHERE version=:version"
                    ),
                    {
                        "version": migration.version,
                        "name": migration.name,
                        "applied_at": utc_now().isoformat(),
                    },
                )
            continue
        with engine.begin() as connection:
            _execute_migration_statements(connection, migration.statements)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations(version, name, applied_at) "
                    "VALUES (:version, :name, :applied_at)"
                ),
                {
                    "version": migration.version,
                    "name": migration.name,
                    "applied_at": utc_now().isoformat(),
                },
            )

    return current_version(engine)


__all__ = ["MIGRATIONS", "Migration", "MigrationError", "current_version", "run_migrations"]
