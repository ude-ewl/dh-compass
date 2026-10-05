"""Repositories for durable web metadata.

Repositories use SQLAlchemy Core deliberately: the stored scenario document is a
JSON/TOML-shaped value and should not be flattened into an ORM model with one
column per ``AppConfig`` field.  All writes are transactional and revisions are
append-only.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from ..services.configuration import ConfigurationAdapter, ConfigurationChange
from .identifiers import new_identifier, utc_now

UNSET = object()


class MetadataNotFound(LookupError):
    """Raised when a requested metadata resource does not exist."""


@dataclass(slots=True)
class RevisionConflict(RuntimeError):
    """Optimistic-lock failure containing the latest revision information."""

    scenario_id: str
    expected_revision_id: str
    current_revision_id: str | None
    current_document: dict[str, Any] | None = None

    def __str__(self) -> str:
        return (
            f"Scenario {self.scenario_id} changed after revision "
            f"{self.expected_revision_id} was read."
        )


@dataclass(frozen=True, slots=True)
class ConfigUpdateResult:
    scenario: dict[str, Any]
    revision: dict[str, Any]
    invalidation: ConfigurationChange
    created: bool


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _json_load(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _timestamp(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _as_iso(value: str | datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else value


def _bool(value: Any) -> bool:
    return bool(int(value))


def _row_mapping(connection, statement: str, parameters: Mapping[str, Any]) -> dict[str, Any] | None:
    row = connection.execute(text(statement), parameters).mappings().first()
    return dict(row) if row is not None else None


def _revision_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    created_at = _timestamp(row.get("created_at"))
    return {
        "id": str(row["id"]),
        "scenario_id": str(row["scenario_id"]),
        "parent_revision_id": row.get("parent_revision_id"),
        "revision_number": int(row["revision_number"]),
        "document": _json_load(row.get("document_json"), {}),
        "created_at": created_at,
        "updated_at": created_at,
    }


def _scenario_dict(row: Mapping[str, Any], revision: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "name": str(row["name"]),
        "description": row.get("description"),
        "archived": _bool(row.get("archived", 0)),
        "current_revision_id": row.get("current_revision_id"),
        "revision_number": int(
            (revision or {}).get("revision_number") or row.get("revision_number") or 0
        ),
        "readiness_state": str(row.get("readiness_state") or "incomplete"),
        "preview_id": row.get("preview_id"),
        "preview_stale_reason": row.get("preview_stale_reason"),
        "run_required": _bool(row.get("run_required", 0)),
        "area_summary": _json_load(row.get("area_summary_json"), {}),
        "effective_lhd_threshold": row.get("effective_lhd_threshold"),
        "expert_override_count": int(row.get("expert_override_count") or 0),
        "created_at": _timestamp(row.get("created_at")),
        "updated_at": _timestamp(row.get("updated_at")),
    }
    if revision is not None:
        result["revision"] = _revision_dict(revision)
    return result


def _project_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "description": row.get("description"),
        "archived": _bool(row.get("archived", 0)),
        "scenario_count": int(row.get("scenario_count") or 0),
        "recent_run_statuses": list(_json_load(row.get("recent_run_statuses_json"), [])),
        "created_at": _timestamp(row.get("created_at")),
        "updated_at": _timestamp(row.get("updated_at")),
    }


def _preview_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    summary = _json_load(row.get("summary_json"), {})
    if not isinstance(summary, dict):
        summary = {}
    return {
        "id": str(row["id"]),
        "scenario_id": str(row["scenario_id"]),
        "scenario_revision_id": str(row["scenario_revision_id"]),
        "status": str(row["status"]),
        "stale_reason": row.get("stale_reason"),
        "linear_heat_density_threshold": row.get("linear_heat_density_threshold"),
        "summary": summary,
        "progress": summary.get("_progress"),
        "started_at": _timestamp(summary.get("_started_at")),
        "finished_at": _timestamp(summary.get("_finished_at")),
        "failure_summary": summary.get("_failure_summary"),
        "warnings": summary.get("_warnings", []),
        "created_at": _timestamp(row.get("created_at")),
        "updated_at": _timestamp(row.get("updated_at")),
    }


def _run_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    progress = _json_load(row.get("progress_json"), {})
    candidate_progress = _json_load(row.get("candidate_progress_json"), {})
    warnings = _json_load(row.get("warnings_json"), [])
    if not isinstance(progress, dict):
        progress = {}
    if not isinstance(candidate_progress, dict):
        candidate_progress = {}
    if not isinstance(warnings, list):
        warnings = []
    process_identity = {
        "pid": row.get("process_pid"),
        "started_at": _timestamp(row.get("process_started_at")),
        "heartbeat_at": _timestamp(row.get("heartbeat_at")),
    }
    if all(value is None for value in process_identity.values()):
        process_identity = None
    solver = {
        "name": row.get("solver_name"),
        "version": row.get("solver_version"),
    }
    if all(value is None for value in solver.values()):
        solver = None
    return {
        "id": str(row["id"]),
        "scenario_id": str(row["scenario_id"]),
        "scenario_revision_id": str(row["scenario_revision_id"]),
        "preview_id": row.get("preview_id"),
        "name": str(row["name"]),
        "description": row.get("description"),
        "status": str(row["status"]),
        "stage": row.get("current_stage"),
        "progress": progress,
        "candidate_progress": candidate_progress,
        "configuration_snapshot": _json_load(
            row.get("configuration_snapshot_json"), {}
        ),
        "failure_summary": row.get("failure_summary"),
        "failure_details": _json_load(row.get("failure_details_json"), {}),
        "warnings": warnings,
        "configuration_version": row.get("configuration_version"),
        "bbox": _json_load(row.get("bbox_json"), None),
        "data_snapshot": _json_load(row.get("data_snapshot_json"), {}),
        "execution_mode": str(row.get("execution_mode") or "standard"),
        "started_at": _timestamp(row.get("started_at")),
        "finished_at": _timestamp(row.get("finished_at")),
        "created_at": _timestamp(row.get("created_at")),
        "updated_at": _timestamp(row.get("updated_at")),
        "output_storage_key": row.get("output_storage_key"),
        "output_label": row.get("output_label"),
        "log_storage_key": row.get("log_storage_key"),
        "manifest_storage_key": row.get("manifest_storage_key"),
        "process_identity": process_identity,
        "application_version": row.get("application_version"),
        "solver": solver,
        "idempotency_key": row.get("idempotency_key"),
    }


class ProjectRepository:
    """CRUD operations for projects and project-level summaries."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def create(self, name: str, description: str | None = None) -> dict[str, Any]:
        project_id = new_identifier()
        now = utc_now().isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO projects "
                    "(id, name, description, archived, created_at, updated_at) "
                    "VALUES (:id, :name, :description, 0, :created_at, :updated_at)"
                ),
                {
                    "id": project_id,
                    "name": name,
                    "description": description,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return self.get(project_id)

    def list(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        condition = "" if include_archived else "WHERE p.archived = 0"
        statement = f"""
            SELECT p.*,
                   COUNT(DISTINCT s.id) AS scenario_count,
                   COALESCE(
                       (SELECT json_group_array(status)
                        FROM (
                            SELECT r.status
                            FROM runs r
                            JOIN scenarios rs ON rs.id = r.scenario_id
                            WHERE rs.project_id = p.id
                            ORDER BY r.updated_at DESC
                            LIMIT 5
                        )), '[]') AS recent_run_statuses_json
            FROM projects p
            LEFT JOIN scenarios s ON s.project_id = p.id AND s.archived = 0
            {condition}
            GROUP BY p.id
            ORDER BY p.updated_at DESC, p.id
        """
        with self.engine.connect() as connection:
            rows = connection.execute(text(statement)).mappings().all()
        return [_project_dict(row) for row in rows]

    def get(self, project_id: str) -> dict[str, Any]:
        statement = """
            SELECT p.*,
                   (SELECT COUNT(*) FROM scenarios s
                    WHERE s.project_id = p.id AND s.archived = 0) AS scenario_count,
                   COALESCE(
                       (SELECT json_group_array(status)
                        FROM (
                            SELECT r.status
                            FROM runs r
                            JOIN scenarios rs ON rs.id = r.scenario_id
                            WHERE rs.project_id = p.id
                            ORDER BY r.updated_at DESC
                            LIMIT 5
                        )), '[]') AS recent_run_statuses_json
            FROM projects p
            WHERE p.id = :id
        """
        with self.engine.connect() as connection:
            row = _row_mapping(connection, statement, {"id": project_id})
        if row is None:
            raise MetadataNotFound(f"Project {project_id} was not found")
        return _project_dict(row)

    def update(
        self,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None | object = UNSET,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        current = self.get(project_id)
        values = {
            "name": current["name"] if name is None else name,
            "description": current["description"] if description is UNSET else description,
            "archived": int(current["archived"] if archived is None else archived),
            "updated_at": utc_now().isoformat(),
            "id": project_id,
        }
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE projects SET name=:name, description=:description, "
                    "archived=:archived, updated_at=:updated_at WHERE id=:id"
                ),
                values,
            )
        return self.get(project_id)

    def archive(self, project_id: str) -> dict[str, Any]:
        return self.update(project_id, archived=True)

    def delete(self, project_id: str) -> None:
        self.get(project_id)
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM projects WHERE id=:id"), {"id": project_id})


class ScenarioRepository:
    """Scenario and immutable revision persistence with optimistic locking."""

    def __init__(self, engine: Engine, adapter: ConfigurationAdapter):
        self.engine = engine
        self.adapter = adapter

    def _row(self, connection, scenario_id: str) -> dict[str, Any] | None:
        return _row_mapping(connection, "SELECT * FROM scenarios WHERE id=:id", {"id": scenario_id})

    def _revision_row(self, connection, revision_id: str | None) -> dict[str, Any] | None:
        if not revision_id:
            return None
        return _row_mapping(
            connection,
            "SELECT * FROM scenario_revisions WHERE id=:id",
            {"id": revision_id},
        )

    def get(self, scenario_id: str, *, include_document: bool = True) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = self._row(connection, scenario_id)
            if row is None:
                raise MetadataNotFound(f"Scenario {scenario_id} was not found")
            revision = self._revision_row(connection, row.get("current_revision_id"))
        return _scenario_dict(row, revision if include_document else None)

    def list_for_project(
        self,
        project_id: str,
        *,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        condition = "" if include_archived else "AND s.archived = 0"
        statement = f"""
            SELECT s.*, r.revision_number
            FROM scenarios s
            LEFT JOIN scenario_revisions r ON r.id = s.current_revision_id
            WHERE s.project_id = :project_id {condition}
            ORDER BY s.updated_at DESC, s.id
        """
        with self.engine.connect() as connection:
            rows = connection.execute(text(statement), {"project_id": project_id}).mappings().all()
        return [_scenario_dict(row) for row in rows]

    def create(
        self,
        project_id: str,
        name: str,
        description: str | None = None,
        *,
        document: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Verify the parent before creating a child.  This also produces the
        # same not-found semantics as all other repository operations.
        with self.engine.connect() as connection:
            project = connection.execute(
                text("SELECT id FROM projects WHERE id=:id"), {"id": project_id}
            ).first()
        if project is None:
            raise MetadataNotFound(f"Project {project_id} was not found")

        validated = self.adapter.validate(document or self.adapter.defaults)
        scenario_id = new_identifier()
        revision_id = new_identifier()
        now = utc_now().isoformat()
        threshold = validated.document.get("network", {}).get("linear_heat_density_threshold")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO scenarios "
                    "(id, project_id, name, description, archived, current_revision_id, "
                    "readiness_state, preview_id, preview_stale_reason, run_required, "
                    "area_summary_json, effective_lhd_threshold, expert_override_count, "
                    "created_at, updated_at) "
                    "VALUES (:id, :project_id, :name, :description, 0, :revision_id, "
                    "'incomplete', NULL, NULL, 0, '{}', :threshold, :expert_count, :created_at, :updated_at)"
                ),
                {
                    "id": scenario_id,
                    "project_id": project_id,
                    "name": name,
                    "description": description,
                    "revision_id": revision_id,
                    "threshold": threshold,
                    "expert_count": validated.expert_override_count,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO scenario_revisions "
                    "(id, scenario_id, parent_revision_id, revision_number, document_json, created_at) "
                    "VALUES (:id, :scenario_id, NULL, 1, :document_json, :created_at)"
                ),
                {
                    "id": revision_id,
                    "scenario_id": scenario_id,
                    "document_json": _json_dump(validated.document),
                    "created_at": now,
                },
            )
        return self.get(scenario_id)

    def update_metadata(
        self,
        scenario_id: str,
        *,
        expected_revision_id: str,
        name: str | None | object = UNSET,
        description: str | None | object = UNSET,
        archived: bool | object = UNSET,
    ) -> dict[str, Any]:
        """Save scenario metadata as a new immutable revision when it changes.

        Metadata edits participate in the same revision token as configuration
        edits.  Otherwise two editors can both satisfy the unchanged
        ``current_revision_id`` and silently overwrite one another.
        """

        with self.engine.begin() as connection:
            row = self._row(connection, scenario_id)
            if row is None:
                raise MetadataNotFound(f"Scenario {scenario_id} was not found")
            self._ensure_revision(row, scenario_id, expected_revision_id, connection)
            current_revision = self._revision_row(connection, row.get("current_revision_id"))
            if current_revision is None:
                raise MetadataNotFound(f"Scenario {scenario_id} has no configuration revision")

            values = {
                "name": row["name"] if name is UNSET else name,
                "description": row.get("description") if description is UNSET else description,
                "archived": int(row.get("archived", 0) if archived is UNSET else archived),
            }
            if (
                values["name"] == row["name"]
                and values["description"] == row.get("description")
                and values["archived"] == int(row.get("archived", 0))
            ):
                return _scenario_dict(row, current_revision)

            revision_id = new_identifier()
            now = utc_now().isoformat()
            revision_number = int(current_revision["revision_number"]) + 1
            connection.execute(
                text(
                    "INSERT INTO scenario_revisions "
                    "(id, scenario_id, parent_revision_id, revision_number, document_json, created_at) "
                    "VALUES (:id, :scenario_id, :parent_id, :revision_number, :document_json, :created_at)"
                ),
                {
                    "id": revision_id,
                    "scenario_id": scenario_id,
                    "parent_id": current_revision["id"],
                    "revision_number": revision_number,
                    "document_json": current_revision["document_json"],
                    "created_at": now,
                },
            )
            updated = connection.execute(
                text(
                    "UPDATE scenarios SET name=:name, description=:description, archived=:archived, "
                    "current_revision_id=:revision_id, updated_at=:updated_at "
                    "WHERE id=:id AND current_revision_id=:expected"
                ),
                {
                    **values,
                    "revision_id": revision_id,
                    "updated_at": now,
                    "id": scenario_id,
                    "expected": expected_revision_id,
                },
            )
            if updated.rowcount != 1:
                self._raise_conflict(connection, scenario_id, expected_revision_id)
        return self.get(scenario_id)

    def update_config(
        self,
        scenario_id: str,
        *,
        expected_revision_id: str,
        document: Mapping[str, Any],
        replace: bool = False,
    ) -> ConfigUpdateResult:
        with self.engine.begin() as connection:
            row = self._row(connection, scenario_id)
            if row is None:
                raise MetadataNotFound(f"Scenario {scenario_id} was not found")
            current_revision = self._revision_row(connection, row.get("current_revision_id"))
            if current_revision is None:
                raise MetadataNotFound(f"Scenario {scenario_id} has no configuration revision")
            self._ensure_revision(row, scenario_id, expected_revision_id, connection)
            current_document = _json_load(current_revision.get("document_json"), {})
            validated = self.adapter.validate(
                document,
                base_document=current_document,
                replace=replace,
            )
            invalidation = self.adapter.change(current_document, validated.document)
            if not invalidation.changed_paths:
                return ConfigUpdateResult(
                    scenario=_scenario_dict(row, current_revision),
                    revision=_revision_dict(current_revision),
                    invalidation=invalidation,
                    created=False,
                )

            revision_id = new_identifier()
            now = utc_now().isoformat()
            revision_number = int(current_revision["revision_number"]) + 1
            threshold = validated.document.get("network", {}).get(
                "linear_heat_density_threshold"
            )
            stale_reason = (
                "; ".join(invalidation.reasons)
                if invalidation.preview_invalidated
                else row.get("preview_stale_reason")
            )
            run_required = int(
                bool(row.get("run_required", 0)) or invalidation.new_run_required
            )
            readiness_state = str(row.get("readiness_state") or "incomplete")
            if invalidation.preview_invalidated:
                readiness_state = "stale"
            connection.execute(
                text(
                    "INSERT INTO scenario_revisions "
                    "(id, scenario_id, parent_revision_id, revision_number, document_json, created_at) "
                    "VALUES (:id, :scenario_id, :parent_id, :revision_number, :document_json, :created_at)"
                ),
                {
                    "id": revision_id,
                    "scenario_id": scenario_id,
                    "parent_id": current_revision["id"],
                    "revision_number": revision_number,
                    "document_json": _json_dump(validated.document),
                    "created_at": now,
                },
            )
            updated = connection.execute(
                text(
                    "UPDATE scenarios SET current_revision_id=:revision_id, "
                    "readiness_state=:readiness_state, preview_stale_reason=:stale_reason, "
                    "run_required=:run_required, effective_lhd_threshold=:threshold, "
                    "expert_override_count=:expert_count, updated_at=:updated_at "
                    "WHERE id=:id AND current_revision_id=:expected"
                ),
                {
                    "revision_id": revision_id,
                    "readiness_state": readiness_state,
                    "stale_reason": stale_reason,
                    "run_required": run_required,
                    "threshold": threshold,
                    "expert_count": validated.expert_override_count,
                    "updated_at": now,
                    "id": scenario_id,
                    "expected": expected_revision_id,
                },
            )
            if updated.rowcount != 1:
                self._raise_conflict(connection, scenario_id, expected_revision_id)
            if invalidation.preview_invalidated:
                connection.execute(
                    text(
                        "UPDATE previews SET status='stale', stale_reason=:reason, updated_at=:updated_at "
                        "WHERE scenario_id=:scenario_id AND status NOT IN ('cancelled', 'failed')"
                    ),
                    {
                        "reason": stale_reason,
                        "updated_at": now,
                        "scenario_id": scenario_id,
                    },
                )
            new_row = self._row(connection, scenario_id)
            new_revision = self._revision_row(connection, revision_id)
        assert new_row is not None and new_revision is not None
        return ConfigUpdateResult(
            scenario=_scenario_dict(new_row, new_revision),
            revision=_revision_dict(new_revision),
            invalidation=invalidation,
            created=True,
        )

    def duplicate(
        self,
        scenario_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        source = self.get(scenario_id)
        return self.create(
            source["project_id"],
            name or f"{source['name']} copy",
            source["description"] if description is None else description,
            document=source["revision"]["document"],
        )

    def get_revision(self, scenario_id: str, revision_id: str) -> dict[str, Any]:
        """Return one immutable revision after checking its scenario owner."""

        self.get(scenario_id, include_document=False)
        with self.engine.connect() as connection:
            row = _row_mapping(
                connection,
                "SELECT * FROM scenario_revisions "
                "WHERE scenario_id=:scenario_id AND id=:revision_id",
                {"scenario_id": scenario_id, "revision_id": revision_id},
            )
        if row is None:
            raise MetadataNotFound(
                f"Revision {revision_id} for scenario {scenario_id} was not found"
            )
        return _revision_dict(row)

    def revisions(self, scenario_id: str) -> list[dict[str, Any]]:
        self.get(scenario_id, include_document=False)
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT * FROM scenario_revisions WHERE scenario_id=:scenario_id "
                    "ORDER BY revision_number DESC"
                ),
                {"scenario_id": scenario_id},
            ).mappings().all()
        return [_revision_dict(row) for row in rows]

    def _ensure_revision(
        self,
        row: Mapping[str, Any],
        scenario_id: str,
        expected_revision_id: str,
        connection,
    ) -> None:
        if row.get("current_revision_id") != expected_revision_id:
            self._raise_conflict(connection, scenario_id, expected_revision_id)

    def _raise_conflict(self, connection, scenario_id: str, expected_revision_id: str) -> None:
        row = self._row(connection, scenario_id)
        current_revision_id = row.get("current_revision_id") if row else None
        revision = self._revision_row(connection, current_revision_id)
        raise RevisionConflict(
            scenario_id=scenario_id,
            expected_revision_id=expected_revision_id,
            current_revision_id=current_revision_id,
            current_document=(
                _json_load(revision.get("document_json"), {}) if revision is not None else None
            ),
        )


class StudyAreaRepository:
    """Persist display geometry independently from the execution bbox."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def get(self, scenario_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = _row_mapping(
                connection,
                "SELECT * FROM study_areas WHERE scenario_id=:scenario_id",
                {"scenario_id": scenario_id},
            )
        if row is None:
            return None
        return {
            "scenario_id": str(row["scenario_id"]),
            "display_geometry": _json_load(row.get("display_geometry_json"), None),
            "execution_bbox": _json_load(row.get("execution_bbox_json"), []),
            "source": str(row.get("source") or "bbox"),
            "imported_filename": row.get("imported_filename"),
            "crs": row.get("crs"),
            "validation_issues": _json_load(row.get("validation_json"), []),
            "updated_at": _timestamp(row.get("updated_at")),
        }

    def save(
        self,
        scenario_id: str,
        *,
        display_geometry: Mapping[str, Any] | None,
        execution_bbox: list[float],
        source: str,
        imported_filename: str | None = None,
        crs: str | None = None,
        validation_issues: list[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        now = utc_now().isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO study_areas "
                    "(scenario_id, display_geometry_json, execution_bbox_json, source, "
                    "imported_filename, crs, validation_json, updated_at) "
                    "VALUES (:scenario_id, :geometry, :bbox, :source, :filename, :crs, :issues, :updated_at) "
                    "ON CONFLICT(scenario_id) DO UPDATE SET "
                    "display_geometry_json=excluded.display_geometry_json, "
                    "execution_bbox_json=excluded.execution_bbox_json, source=excluded.source, "
                    "imported_filename=excluded.imported_filename, crs=excluded.crs, "
                    "validation_json=excluded.validation_json, updated_at=excluded.updated_at"
                ),
                {
                    "scenario_id": scenario_id,
                    "geometry": _json_dump(display_geometry) if display_geometry is not None else None,
                    "bbox": _json_dump(execution_bbox),
                    "source": source,
                    "filename": imported_filename,
                    "crs": crs,
                    "issues": _json_dump(validation_issues or []),
                    "updated_at": now,
                },
            )
            connection.execute(
                text(
                    "UPDATE scenarios SET area_summary_json=:summary, updated_at=:updated_at "
                    "WHERE id=:scenario_id"
                ),
                {
                    "scenario_id": scenario_id,
                    "summary": _json_dump(
                        {
                            "execution_bbox": execution_bbox,
                            "source": source,
                            "has_display_geometry": display_geometry is not None,
                            "imported_filename": imported_filename,
                        }
                    ),
                    "updated_at": now,
                },
            )
        result = self.get(scenario_id)
        assert result is not None
        return result


class DatasetStateRepository:
    """Persist the last known validation state without storing source files."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def set(
        self,
        scenario_id: str,
        dataset_id: str,
        *,
        status: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now().isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO dataset_states "
                    "(scenario_id, dataset_id, status, metadata_json, updated_at) "
                    "VALUES (:scenario_id, :dataset_id, :status, :metadata, :updated_at) "
                    "ON CONFLICT(scenario_id, dataset_id) DO UPDATE SET "
                    "status=excluded.status, metadata_json=excluded.metadata_json, "
                    "updated_at=excluded.updated_at"
                ),
                {
                    "scenario_id": scenario_id,
                    "dataset_id": dataset_id,
                    "status": status,
                    "metadata": _json_dump(metadata or {}),
                    "updated_at": now,
                },
            )
        return {
            "scenario_id": scenario_id,
            "dataset_id": dataset_id,
            "status": status,
            "metadata": dict(metadata or {}),
            "updated_at": _timestamp(now),
        }

    def list_for_scenario(self, scenario_id: str) -> dict[str, dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT * FROM dataset_states WHERE scenario_id=:scenario_id"),
                {"scenario_id": scenario_id},
            ).mappings().all()
        return {
            str(row["dataset_id"]): {
                "status": str(row["status"]),
                "metadata": _json_load(row.get("metadata_json"), {}),
                "updated_at": _timestamp(row.get("updated_at")),
            }
            for row in rows
        }


class PreviewRepository:
    """Persistence boundary for preview job metadata."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def create(
        self,
        scenario_id: str,
        scenario_revision_id: str,
        *,
        threshold: float | None = None,
        status: str = "queued",
    ) -> dict[str, Any]:
        preview_id = new_identifier()
        now = utc_now().isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO previews "
                    "(id, scenario_id, scenario_revision_id, status, stale_reason, "
                    "linear_heat_density_threshold, summary_json, created_at, updated_at) "
                    "VALUES (:id, :scenario_id, :revision_id, :status, NULL, :threshold, '{}', :now, :now)"
                ),
                {
                    "id": preview_id,
                    "scenario_id": scenario_id,
                    "revision_id": scenario_revision_id,
                    "status": status,
                    "threshold": threshold,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    "UPDATE scenarios SET preview_id=:preview_id, preview_stale_reason=NULL, "
                    "updated_at=:now WHERE id=:scenario_id"
                ),
                {"preview_id": preview_id, "now": now, "scenario_id": scenario_id},
            )
        return self.get(preview_id)

    def get(self, preview_id: str) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = _row_mapping(connection, "SELECT * FROM previews WHERE id=:id", {"id": preview_id})
        if row is None:
            raise MetadataNotFound(f"Preview {preview_id} was not found")
        return _preview_dict(row)

    def update_status(
        self,
        preview_id: str,
        status: str,
        *,
        stage: str | None = None,
        completed: int | None = None,
        total: int | None = None,
        fraction: float | None = None,
        failure_summary: str | None = None,
        warnings: list[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        current = self.get(preview_id)
        summary = dict(current.get("summary") or {})
        if stage is not None or completed is not None or total is not None or fraction is not None:
            summary["_progress"] = {
                "stage": stage,
                "completed": completed,
                "total": total,
                "fraction": fraction,
            }
        now = utc_now().isoformat()
        if status == "running" and current.get("started_at") is None:
            summary["_started_at"] = now
        if status in {"ready", "failed", "cancelled"}:
            summary["_finished_at"] = now
        if failure_summary is not None:
            summary["_failure_summary"] = failure_summary
        if warnings is not None:
            summary["_warnings"] = list(warnings)
        with self.engine.begin() as connection:
            updated = connection.execute(
                text(
                    "UPDATE previews SET status=:status, stale_reason=:stale_reason, "
                    "summary_json=:summary, updated_at=:updated_at WHERE id=:id"
                ),
                {
                    "status": status,
                    "stale_reason": current.get("stale_reason") if status != "stale" else current.get("stale_reason"),
                    "summary": _json_dump(summary),
                    "updated_at": now,
                    "id": preview_id,
                },
            )
            if updated.rowcount != 1:
                raise MetadataNotFound(f"Preview {preview_id} was not found")
            if status == "running":
                connection.execute(
                    text(
                        "UPDATE scenarios SET readiness_state='running', updated_at=:now "
                        "WHERE id=:scenario_id"
                    ),
                    {"now": now, "scenario_id": current["scenario_id"]},
                )
            elif status == "ready":
                connection.execute(
                    text(
                        "UPDATE scenarios SET readiness_state='complete', preview_stale_reason=NULL, "
                        "updated_at=:now WHERE id=:scenario_id AND preview_id=:preview_id"
                    ),
                    {"now": now, "scenario_id": current["scenario_id"], "preview_id": preview_id},
                )
            elif status in {"failed", "cancelled"}:
                connection.execute(
                    text(
                        "UPDATE scenarios SET readiness_state='warning', updated_at=:now "
                        "WHERE id=:scenario_id AND preview_id=:preview_id"
                    ),
                    {"now": now, "scenario_id": current["scenario_id"], "preview_id": preview_id},
                )
        return self.get(preview_id)

    def set_summary(self, preview_id: str, summary: Mapping[str, Any]) -> dict[str, Any]:
        current = self.get(preview_id)
        merged = dict(current.get("summary") or {})
        merged.update(dict(summary))
        with self.engine.begin() as connection:
            updated = connection.execute(
                text(
                    "UPDATE previews SET summary_json=:summary, updated_at=:updated_at WHERE id=:id"
                ),
                {
                    "summary": _json_dump(merged),
                    "updated_at": utc_now().isoformat(),
                    "id": preview_id,
                },
            )
            if updated.rowcount != 1:
                raise MetadataNotFound(f"Preview {preview_id} was not found")
        return self.get(preview_id)

    def mark_stale(self, preview_id: str, reason: str) -> dict[str, Any]:
        current = self.get(preview_id)
        summary = dict(current.get("summary") or {})
        now = utc_now().isoformat()
        summary.pop("_progress", None)
        with self.engine.begin() as connection:
            updated = connection.execute(
                text(
                    "UPDATE previews SET status='stale', stale_reason=:reason, summary_json=:summary, updated_at=:now "
                    "WHERE id=:id"
                ),
                {"reason": reason, "summary": _json_dump(summary), "now": now, "id": preview_id},
            )
            if updated.rowcount != 1:
                raise MetadataNotFound(f"Preview {preview_id} was not found")
            connection.execute(
                text(
                    "UPDATE scenarios SET readiness_state='stale', preview_stale_reason=:reason, updated_at=:now "
                    "WHERE id=:scenario_id AND preview_id=:preview_id"
                ),
                {
                    "reason": reason,
                    "now": now,
                    "scenario_id": current["scenario_id"],
                    "preview_id": preview_id,
                },
            )
        return self.get(preview_id)

    def for_scenario(self, scenario_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT * FROM previews WHERE scenario_id=:scenario_id ORDER BY created_at DESC"),
                {"scenario_id": scenario_id},
            ).mappings().all()
        return [_preview_dict(row) for row in rows]


class CalculationRequestRepository:
    """Durable idempotency records for the one-command calculation API."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def get(self, idempotency_key: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = _row_mapping(
                connection,
                "SELECT * FROM calculation_requests WHERE idempotency_key=:key",
                {"key": idempotency_key},
            )
        if row is None:
            return None
        return {
            "idempotency_key": str(row["idempotency_key"]),
            "bbox": _json_load(row.get("bbox_json"), []),
            "run_id": row.get("run_id"),
            "status": str(row.get("status") or "in_progress"),
            "created_at": _timestamp(row.get("created_at")),
            "updated_at": _timestamp(row.get("updated_at")),
        }

    def create_submission(
        self,
        idempotency_key: str,
        bbox: list[float],
        *,
        configuration_snapshot: Mapping[str, Any],
        expert_override_count: int,
        configuration_version: str,
        application_version: str,
        display_geometry: Mapping[str, Any],
    ) -> str:
        """Atomically create a calculation's internal records and its key.

        The unique idempotency row is deliberately inserted in the same
        transaction as the project, scenario, revision, study area, and run.
        A concurrent request therefore either observes the fully-created run
        or loses the unique-key race; it can never observe a durable
        reservation that has no run identity.
        """

        project_id = new_identifier()
        scenario_id = new_identifier()
        revision_id = new_identifier()
        run_id = new_identifier()
        now = utc_now().isoformat()
        network = configuration_snapshot.get("network")
        threshold = (
            network.get("linear_heat_density_threshold")
            if isinstance(network, Mapping)
            else None
        )
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO projects "
                    "(id, name, description, archived, created_at, updated_at) "
                    "VALUES (:id, :name, :description, 0, :now, :now)"
                ),
                {
                    "id": project_id,
                    "name": "Calculation workspace",
                    "description": "Internal workspace created by the one-command calculation.",
                    "now": now,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO scenarios "
                    "(id, project_id, name, description, archived, current_revision_id, "
                    "readiness_state, preview_id, preview_stale_reason, run_required, "
                    "area_summary_json, effective_lhd_threshold, expert_override_count, "
                    "created_at, updated_at) "
                    "VALUES (:id, :project_id, :name, :description, 0, :revision_id, "
                    "'incomplete', NULL, NULL, 0, :area_summary, :threshold, :expert_count, :now, :now)"
                ),
                {
                    "id": scenario_id,
                    "project_id": project_id,
                    "name": "Study area calculation",
                    "description": "Internal scenario for a one-command calculation.",
                    "revision_id": revision_id,
                    "area_summary": _json_dump(
                        {
                            "execution_bbox": bbox,
                            "source": "bbox",
                            "has_display_geometry": True,
                        }
                    ),
                    "threshold": threshold,
                    "expert_count": expert_override_count,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO scenario_revisions "
                    "(id, scenario_id, parent_revision_id, revision_number, document_json, created_at) "
                    "VALUES (:id, :scenario_id, NULL, 1, :document, :now)"
                ),
                {
                    "id": revision_id,
                    "scenario_id": scenario_id,
                    "document": _json_dump(configuration_snapshot),
                    "now": now,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO study_areas "
                    "(scenario_id, display_geometry_json, execution_bbox_json, source, "
                    "imported_filename, crs, validation_json, updated_at) "
                    "VALUES (:scenario_id, :geometry, :bbox, 'bbox', NULL, 'EPSG:4326', '[]', :now)"
                ),
                {
                    "scenario_id": scenario_id,
                    "geometry": _json_dump(display_geometry),
                    "bbox": _json_dump(bbox),
                    "now": now,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO runs "
                    "(id, scenario_id, scenario_revision_id, preview_id, name, description, "
                    "status, warnings_json, configuration_snapshot_json, application_version, "
                    "idempotency_key, output_label, configuration_version, bbox_json, "
                    "data_snapshot_json, execution_mode, created_at, updated_at) VALUES "
                    "(:id, :scenario_id, :revision_id, NULL, :name, :description, 'queued', "
                    "'[]', :configuration, :application_version, :idempotency_key, NULL, "
                    ":configuration_version, :bbox, '{}', 'calculation', :now, :now)"
                ),
                {
                    "id": run_id,
                    "scenario_id": scenario_id,
                    "revision_id": revision_id,
                    "name": "Heat-grid calculation",
                    "description": "Created from the selected study area.",
                    "configuration": _json_dump(configuration_snapshot),
                    "application_version": application_version,
                    "idempotency_key": idempotency_key,
                    "configuration_version": configuration_version,
                    "bbox": _json_dump(bbox),
                    "now": now,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO calculation_requests "
                    "(idempotency_key, bbox_json, run_id, status, created_at, updated_at) "
                    "VALUES (:key, :bbox, :run_id, 'accepted', :now, :now)"
                ),
                {
                    "key": idempotency_key,
                    "bbox": _json_dump(bbox),
                    "run_id": run_id,
                    "now": now,
                },
            )
        return run_id


class RunRepository:
    """Durable run state, immutable snapshots, and worker heartbeats."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def get(self, run_id: str) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = _row_mapping(connection, "SELECT * FROM runs WHERE id=:id", {"id": run_id})
        if row is None:
            raise MetadataNotFound(f"Run {run_id} was not found")
        return _run_dict(row)

    def find_by_idempotency(self, scenario_id: str, idempotency_key: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = _row_mapping(
                connection,
                "SELECT * FROM runs WHERE scenario_id=:scenario_id AND idempotency_key=:key",
                {"scenario_id": scenario_id, "key": idempotency_key},
            )
        return _run_dict(row) if row is not None else None

    def list_for_project(self, project_id: str) -> list[dict[str, Any]]:
        statement = """
            SELECT r.* FROM runs r
            JOIN scenarios s ON s.id = r.scenario_id
            WHERE s.project_id=:project_id
            ORDER BY r.updated_at DESC, r.id
        """
        with self.engine.connect() as connection:
            rows = connection.execute(text(statement), {"project_id": project_id}).mappings().all()
        return [_run_dict(row) for row in rows]

    def list_for_scenario(self, scenario_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT * FROM runs WHERE scenario_id=:scenario_id ORDER BY updated_at DESC, id"),
                {"scenario_id": scenario_id},
            ).mappings().all()
        return [_run_dict(row) for row in rows]

    def list_by_status(self, statuses: tuple[str, ...]) -> list[dict[str, Any]]:
        if not statuses:
            return []
        placeholders = ", ".join(f":status_{index}" for index in range(len(statuses)))
        parameters = {f"status_{index}": value for index, value in enumerate(statuses)}
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(f"SELECT * FROM runs WHERE status IN ({placeholders}) ORDER BY created_at, id"),
                parameters,
            ).mappings().all()
        return [_run_dict(row) for row in rows]

    def count(self) -> int:
        """Return the number of durable run records.

        Paged listings report this instead of the size of one fetched window,
        so ``total`` and ``has_next`` describe the whole collection.
        """

        with self.engine.connect() as connection:
            return int(connection.execute(text("SELECT COUNT(*) FROM runs")).scalar_one())

    def list_recent(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Return the most recently touched runs for recovery.

        Ordering falls back to ``created_at`` so a run that never received a
        worker heartbeat still appears in a stable position. ``offset`` pages
        through the same ordering used by :meth:`count`.
        """

        statement = """
            SELECT * FROM runs
            ORDER BY COALESCE(updated_at, created_at) DESC, id
            LIMIT :limit OFFSET :offset
        """
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(statement),
                {
                    "limit": max(1, min(int(limit), 200)),
                    "offset": max(0, int(offset)),
                },
            ).mappings().all()
        return [_run_dict(row) for row in rows]

    def create(
        self,
        scenario_id: str,
        scenario_revision_id: str,
        name: str,
        *,
        configuration_snapshot: Mapping[str, Any],
        description: str | None = None,
        preview_id: str | None = None,
        idempotency_key: str | None = None,
        application_version: str | None = None,
        output_label: str | None = None,
        configuration_version: str | None = None,
        bbox: list[float] | None = None,
        data_snapshot: Mapping[str, Any] | None = None,
        execution_mode: str = "standard",
    ) -> dict[str, Any]:
        run_id = new_identifier()
        now = utc_now().isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO runs (id, scenario_id, scenario_revision_id, preview_id, name, description, "
                    "status, warnings_json, configuration_snapshot_json, application_version, "
                    "idempotency_key, output_label, configuration_version, bbox_json, "
                    "data_snapshot_json, execution_mode, created_at, updated_at) VALUES "
                    "(:id, :scenario_id, :revision_id, :preview_id, :name, :description, 'queued', '[]', "
                    ":configuration, :application_version, :idempotency_key, :output_label, "
                    ":configuration_version, :bbox, :data_snapshot, :execution_mode, :now, :now)"
                ),
                {
                    "id": run_id,
                    "scenario_id": scenario_id,
                    "revision_id": scenario_revision_id,
                    "preview_id": preview_id,
                    "name": name,
                    "description": description,
                    "configuration": _json_dump(configuration_snapshot),
                    "application_version": application_version,
                    "idempotency_key": idempotency_key,
                    "output_label": output_label,
                    "configuration_version": configuration_version,
                    "bbox": _json_dump(bbox) if bbox is not None else None,
                    "data_snapshot": _json_dump(data_snapshot or {}),
                    "execution_mode": execution_mode,
                    "now": now,
                },
            )
        return self.get(run_id)

    def set_preview_id(self, run_id: str, preview_id: str) -> dict[str, Any]:
        with self.engine.begin() as connection:
            updated = connection.execute(
                text(
                    "UPDATE runs SET preview_id=:preview_id, updated_at=:updated_at "
                    "WHERE id=:id"
                ),
                {
                    "preview_id": preview_id,
                    "updated_at": utc_now().isoformat(),
                    "id": run_id,
                },
            )
            if updated.rowcount != 1:
                raise MetadataNotFound(f"Run {run_id} was not found")
        return self.get(run_id)

    def set_execution_mode(self, run_id: str, execution_mode: str) -> dict[str, Any]:
        with self.engine.begin() as connection:
            updated = connection.execute(
                text(
                    "UPDATE runs SET execution_mode=:execution_mode, updated_at=:updated_at "
                    "WHERE id=:id"
                ),
                {
                    "execution_mode": execution_mode,
                    "updated_at": utc_now().isoformat(),
                    "id": run_id,
                },
            )
            if updated.rowcount != 1:
                raise MetadataNotFound(f"Run {run_id} was not found")
        return self.get(run_id)

    def set_data_snapshot(
        self, run_id: str, data_snapshot: Mapping[str, Any]
    ) -> dict[str, Any]:
        with self.engine.begin() as connection:
            updated = connection.execute(
                text(
                    "UPDATE runs SET data_snapshot_json=:data_snapshot, updated_at=:updated_at "
                    "WHERE id=:id"
                ),
                {
                    "data_snapshot": _json_dump(data_snapshot),
                    "updated_at": utc_now().isoformat(),
                    "id": run_id,
                },
            )
            if updated.rowcount != 1:
                raise MetadataNotFound(f"Run {run_id} was not found")
        return self.get(run_id)

    def create_placeholder(
        self,
        scenario_id: str,
        scenario_revision_id: str,
        name: str,
        *,
        description: str | None = None,
        preview_id: str | None = None,
    ) -> dict[str, Any]:
        """Retain the Milestone 2 helper for callers that only need history."""

        return self.create(
            scenario_id,
            scenario_revision_id,
            name,
            description=description,
            preview_id=preview_id,
            configuration_snapshot={},
        )

    def update_status(
        self,
        run_id: str,
        status: str,
        *,
        stage: str | None = None,
        progress: Mapping[str, Any] | None = None,
        candidate_progress: Mapping[str, Any] | None = None,
        failure_summary: str | None = None,
        failure_details: Mapping[str, Any] | None = None,
        warnings: list[Any] | None = None,
        heartbeat: bool = False,
    ) -> dict[str, Any]:
        current = self.get(run_id)
        terminal_statuses = {"completed", "failed", "cancelled"}
        if current.get("status") in terminal_statuses and status != current.get("status"):
            # A stale worker from a previous API process must not resurrect a
            # terminal run after startup reconciliation.
            return current
        merged_progress = dict(current.get("progress") or {})
        merged_candidates = dict(current.get("candidate_progress") or {})
        if progress is not None:
            merged_progress.update(dict(progress))
        if candidate_progress is not None:
            merged_candidates.update(dict(candidate_progress))
        now = utc_now().isoformat()
        effective_status = (
            "cancellation_requested"
            if current.get("status") == "cancellation_requested"
            and status not in terminal_statuses
            else status
        )
        started_at = current.get("started_at")
        finished_at = current.get("finished_at")
        if effective_status == "running" and started_at is None:
            started_at = _timestamp(now)
        if effective_status in {"completed", "failed", "cancelled"}:
            finished_at = _timestamp(now)
        values = {
            "status": effective_status,
            "stage": stage if stage is not None else current.get("stage"),
            "progress": _json_dump(merged_progress),
            "candidate_progress": _json_dump(merged_candidates),
            "failure_summary": (
                failure_summary if failure_summary is not None else current.get("failure_summary")
            ),
            "failure_details": _json_dump(
                failure_details
                if failure_details is not None
                else current.get("failure_details") or {}
            ),
            "warnings": _json_dump(warnings if warnings is not None else current.get("warnings") or []),
            "started_at": started_at.isoformat() if isinstance(started_at, datetime) else started_at,
            "finished_at": finished_at.isoformat() if isinstance(finished_at, datetime) else finished_at,
            "heartbeat_at": now
            if heartbeat or effective_status in {"running", "cancellation_requested"}
            else _as_iso(
                (current.get("process_identity") or {}).get("heartbeat_at")
                if isinstance(current.get("process_identity"), Mapping)
                else None
            ),
            "updated_at": now,
            "id": run_id,
        }
        with self.engine.begin() as connection:
            updated = connection.execute(
                text(
                    "UPDATE runs SET status=:status, current_stage=:stage, progress_json=:progress, "
                    "candidate_progress_json=:candidate_progress, failure_summary=:failure_summary, "
                    "failure_details_json=:failure_details, warnings_json=:warnings, started_at=:started_at, "
                    "finished_at=:finished_at, heartbeat_at=:heartbeat_at, updated_at=:updated_at WHERE id=:id"
                ),
                values,
            )
            if updated.rowcount != 1:
                raise MetadataNotFound(f"Run {run_id} was not found")
        return self.get(run_id)

    def set_process_identity(
        self,
        run_id: str,
        *,
        pid: int | None,
        started_at: datetime | None = None,
        heartbeat_at: datetime | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.engine.begin() as connection:
            if pid is None:
                updated = connection.execute(
                    text(
                        "UPDATE runs SET process_pid=NULL, updated_at=:updated_at WHERE id=:id"
                    ),
                    {"updated_at": now.isoformat(), "id": run_id},
                )
            else:
                updated = connection.execute(
                    text(
                        "UPDATE runs SET process_pid=:pid, process_started_at=:started_at, "
                        "heartbeat_at=:heartbeat_at, updated_at=:updated_at WHERE id=:id"
                    ),
                    {
                        "pid": pid,
                        "started_at": (started_at or now).isoformat(),
                        "heartbeat_at": (heartbeat_at or now).isoformat(),
                        "updated_at": now.isoformat(),
                        "id": run_id,
                    },
                )
            if updated.rowcount != 1:
                raise MetadataNotFound(f"Run {run_id} was not found")
        return self.get(run_id)

    def set_output(
        self,
        run_id: str,
        *,
        output_storage_key: str | None = None,
        log_storage_key: str | None = None,
        manifest_storage_key: str | None = None,
        solver_name: str | None = None,
        solver_version: str | None = None,
    ) -> dict[str, Any]:
        with self.engine.begin() as connection:
            updated = connection.execute(
                text(
                    "UPDATE runs SET output_storage_key=:output, log_storage_key=:log, "
                    "manifest_storage_key=:manifest, solver_name=:solver_name, "
                    "solver_version=:solver_version, updated_at=:updated_at WHERE id=:id"
                ),
                {
                    "output": output_storage_key,
                    "log": log_storage_key,
                    "manifest": manifest_storage_key,
                    "solver_name": solver_name,
                    "solver_version": solver_version,
                    "updated_at": utc_now().isoformat(),
                    "id": run_id,
                },
            )
            if updated.rowcount != 1:
                raise MetadataNotFound(f"Run {run_id} was not found")
        return self.get(run_id)

    def reconcile_interrupted(self, message: str) -> list[dict[str, Any]]:
        """Mark non-terminal workers from a previous API process as failed."""

        interrupted = self.list_by_status(("running", "cancellation_requested"))
        result: list[dict[str, Any]] = []
        for run in interrupted:
            self.update_status(
                run["id"],
                "failed",
                failure_summary=message,
                failure_details={"code": "WORKER_INTERRUPTED"},
            )
            result.append(self.set_process_identity(run["id"], pid=None))
        return result


class JobEventRepository:
    """Append-only ordered events for preview/run workers."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def append(
        self,
        job_id: str,
        job_kind: str,
        sequence: int,
        event_type: str,
        data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        event_id = new_identifier()
        occurred_at = utc_now().isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO job_events "
                    "(id, job_id, job_kind, sequence, event_type, data_json, occurred_at) "
                    "VALUES (:id, :job_id, :job_kind, :sequence, :event_type, :data_json, :occurred_at)"
                ),
                {
                    "id": event_id,
                    "job_id": job_id,
                    "job_kind": job_kind,
                    "sequence": sequence,
                    "event_type": event_type,
                    "data_json": _json_dump(data or {}),
                    "occurred_at": occurred_at,
                },
            )
        return {
            "id": event_id,
            "job_id": job_id,
            "job_kind": job_kind,
            "sequence": sequence,
            "event_type": event_type,
            "data": dict(data or {}),
            "occurred_at": datetime.fromisoformat(occurred_at),
        }

    def next_sequence(self, job_id: str, job_kind: str) -> int:
        with self.engine.connect() as connection:
            value = connection.execute(
                text(
                    "SELECT COALESCE(MAX(sequence), 0) FROM job_events "
                    "WHERE job_id=:job_id AND job_kind=:job_kind"
                ),
                {"job_id": job_id, "job_kind": job_kind},
            ).scalar_one()
        return int(value) + 1

    def append_ordered(
        self,
        job_id: str,
        job_kind: str,
        event_type: str,
        data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append after the current sequence, retrying concurrent writers.

        Worker heartbeats and API cancellation can append at the same time.
        Sequence allocation is intentionally kept in SQLite; a unique-index
        collision simply means another writer won the race for that number.
        """

        for attempt in range(8):
            sequence = self.next_sequence(job_id, job_kind)
            try:
                return self.append(job_id, job_kind, sequence, event_type, data)
            except IntegrityError as exc:
                message = str(getattr(exc, "orig", exc))
                if "UNIQUE constraint" not in message or attempt == 7:
                    raise
        raise AssertionError("unreachable event append retry")

    def list(self, job_id: str, job_kind: str, *, after_sequence: int = 0) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT * FROM job_events WHERE job_id=:job_id AND job_kind=:job_kind "
                    "AND sequence > :after_sequence ORDER BY sequence"
                ),
                {
                    "job_id": job_id,
                    "job_kind": job_kind,
                    "after_sequence": after_sequence,
                },
            ).mappings().all()
        return [
            {
                "id": row["id"],
                "job_id": row["job_id"],
                "job_kind": row["job_kind"],
                "sequence": int(row["sequence"]),
                "event_type": row["event_type"],
                "data": _json_load(row.get("data_json"), {}),
                "occurred_at": _timestamp(row.get("occurred_at")),
            }
            for row in rows
        ]


class ComparisonRepository:
    """Persist immutable comparison responses for refresh and deep links."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def create(self, run_ids: list[str], result: Mapping[str, Any]) -> dict[str, Any]:
        comparison_id = new_identifier()
        now = utc_now().isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO comparisons "
                    "(id, run_ids_json, result_json, created_at, updated_at) "
                    "VALUES (:id, :run_ids, :result, :created_at, :updated_at)"
                ),
                {
                    "id": comparison_id,
                    "run_ids": _json_dump(run_ids),
                    "result": _json_dump(result),
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return self.get(comparison_id)

    def get(self, comparison_id: str) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = _row_mapping(
                connection,
                "SELECT * FROM comparisons WHERE id=:id",
                {"id": comparison_id},
            )
        if row is None:
            raise MetadataNotFound(f"Comparison {comparison_id} was not found")
        result = _json_load(row.get("result_json"), {})
        if not isinstance(result, dict):
            result = {}
        run_ids = _json_load(row.get("run_ids_json"), [])
        if not isinstance(run_ids, list):
            run_ids = []
        return {
            "id": str(row["id"]),
            "run_ids": [str(item) for item in run_ids],
            "result": result,
            "created_at": _timestamp(row.get("created_at")),
            "updated_at": _timestamp(row.get("updated_at")),
        }

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT * FROM comparisons ORDER BY updated_at DESC, id "
                    "LIMIT :limit"
                ),
                {"limit": max(1, min(int(limit), 1000))},
            ).mappings().all()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: Mapping[str, Any]) -> dict[str, Any]:
        result = _json_load(row.get("result_json"), {})
        run_ids = _json_load(row.get("run_ids_json"), [])
        return {
            "id": str(row["id"]),
            "run_ids": [str(item) for item in run_ids] if isinstance(run_ids, list) else [],
            "result": result if isinstance(result, dict) else {},
            "created_at": _timestamp(row.get("created_at")),
            "updated_at": _timestamp(row.get("updated_at")),
        }


class ExportJobRepository:
    """Persist report, bundle, and table-export lifecycle metadata."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def create(
        self,
        run_id: str,
        kind: str,
        *,
        display_name: str,
        media_type: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        export_id = new_identifier()
        now = utc_now().isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO export_jobs "
                    "(id, run_id, kind, status, display_name, media_type, metadata_json, created_at, updated_at) "
                    "VALUES (:id, :run_id, :kind, 'queued', :display_name, :media_type, :metadata, :now, :now)"
                ),
                {
                    "id": export_id,
                    "run_id": run_id,
                    "kind": kind,
                    "display_name": display_name,
                    "media_type": media_type,
                    "metadata": _json_dump(metadata or {}),
                    "now": now,
                },
            )
        return self.get(export_id)

    def get(self, export_id: str) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = _row_mapping(
                connection,
                "SELECT * FROM export_jobs WHERE id=:id",
                {"id": export_id},
            )
        if row is None:
            raise MetadataNotFound(f"Export {export_id} was not found")
        return self._dict(row)

    def update(
        self,
        export_id: str,
        status: str,
        *,
        storage_key: str | None = None,
        byte_size: int | None = None,
        checksum_sha256: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        current = self.get(export_id)
        with self.engine.begin() as connection:
            updated = connection.execute(
                text(
                    "UPDATE export_jobs SET status=:status, storage_key=:storage_key, "
                    "byte_size=:byte_size, checksum_sha256=:checksum, error=:error, "
                    "updated_at=:updated_at WHERE id=:id"
                ),
                {
                    "status": status,
                    "storage_key": storage_key if storage_key is not None else current.get("storage_key"),
                    "byte_size": byte_size if byte_size is not None else current.get("byte_size"),
                    "checksum": checksum_sha256
                    if checksum_sha256 is not None
                    else current.get("checksum_sha256"),
                    "error": error,
                    "updated_at": utc_now().isoformat(),
                    "id": export_id,
                },
            )
            if updated.rowcount != 1:
                raise MetadataNotFound(f"Export {export_id} was not found")
        return self.get(export_id)

    def list_for_run(self, run_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT * FROM export_jobs WHERE run_id=:run_id ORDER BY created_at, id"),
                {"run_id": run_id},
            ).mappings().all()
        return [self._dict(row) for row in rows]

    @staticmethod
    def _dict(row: Mapping[str, Any]) -> dict[str, Any]:
        metadata = _json_load(row.get("metadata_json"), {})
        return {
            "id": str(row["id"]),
            "run_id": str(row["run_id"]),
            "kind": str(row["kind"]),
            "status": str(row["status"]),
            "display_name": str(row["display_name"]),
            "media_type": str(row["media_type"]),
            "storage_key": row.get("storage_key"),
            "byte_size": row.get("byte_size"),
            "checksum_sha256": row.get("checksum_sha256"),
            "error": row.get("error"),
            "metadata": metadata if isinstance(metadata, dict) else {},
            "created_at": _timestamp(row.get("created_at")),
            "updated_at": _timestamp(row.get("updated_at")),
        }


class AuditRepository:
    """Append structured, non-sensitive operation records."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def append(
        self,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        *,
        data: Mapping[str, Any] | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        record_id = new_identifier()
        occurred_at = utc_now().isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO audit_records "
                    "(id, actor, action, resource_type, resource_id, data_json, occurred_at) "
                    "VALUES (:id, :actor, :action, :resource_type, :resource_id, :data, :occurred_at)"
                ),
                {
                    "id": record_id,
                    "actor": actor,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "data": _json_dump(data or {}),
                    "occurred_at": occurred_at,
                },
            )
        return {
            "id": record_id,
            "actor": actor,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "data": dict(data or {}),
            "occurred_at": datetime.fromisoformat(occurred_at),
        }

    def list(
        self,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = []
        parameters: dict[str, Any] = {"limit": max(1, min(int(limit), 1000))}
        if resource_type is not None:
            clauses.append("resource_type=:resource_type")
            parameters["resource_type"] = resource_type
        if resource_id is not None:
            clauses.append("resource_id=:resource_id")
            parameters["resource_id"] = resource_id
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT * FROM audit_records "
                    f"{where} ORDER BY occurred_at DESC, id DESC LIMIT :limit"
                ),
                parameters,
            ).mappings().all()
        return [
            {
                "id": str(row["id"]),
                "actor": row.get("actor"),
                "action": str(row["action"]),
                "resource_type": str(row["resource_type"]),
                "resource_id": row.get("resource_id"),
                "data": _json_load(row.get("data_json"), {}),
                "occurred_at": _timestamp(row.get("occurred_at")),
            }
            for row in rows
        ]


class ArtifactMetadataRepository:
    """Persist artifact metadata without exposing storage paths to clients."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def create(
        self,
        *,
        display_name: str,
        media_type: str,
        run_id: str | None = None,
        preview_id: str | None = None,
        description: str | None = None,
        storage_key: str | None = None,
        status: str = "pending",
        byte_size: int | None = None,
        checksum_sha256: str | None = None,
    ) -> dict[str, Any]:
        artifact_id = new_identifier()
        now = utc_now().isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO artifact_metadata "
                    "(id, run_id, preview_id, display_name, description, media_type, byte_size, status, "
                    "checksum_sha256, storage_key, created_at, updated_at) "
                    "VALUES (:id, :run_id, :preview_id, :display_name, :description, :media_type, :byte_size, "
                    ":status, :checksum_sha256, :storage_key, :now, :now)"
                ),
                {
                    "id": artifact_id,
                    "run_id": run_id,
                    "preview_id": preview_id,
                    "display_name": display_name,
                    "description": description,
                    "media_type": media_type,
                    "byte_size": byte_size,
                    "status": status,
                    "checksum_sha256": checksum_sha256,
                    "storage_key": storage_key,
                    "now": now,
                },
            )
        with self.engine.connect() as connection:
            row = _row_mapping(
                connection,
                "SELECT * FROM artifact_metadata WHERE id=:id",
                {"id": artifact_id},
            )
        assert row is not None
        return self._dict(row)

    def get(self, artifact_id: str) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = _row_mapping(
                connection,
                "SELECT * FROM artifact_metadata WHERE id=:id",
                {"id": artifact_id},
            )
        if row is None:
            raise MetadataNotFound(f"Artifact {artifact_id} was not found")
        return self._dict(row)

    def list_for_run(self, run_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT * FROM artifact_metadata WHERE run_id=:run_id ORDER BY created_at, id"),
                {"run_id": run_id},
            ).mappings().all()
        return [self._dict(row) for row in rows]

    def list_for_preview(self, preview_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT * FROM artifact_metadata WHERE preview_id=:preview_id ORDER BY created_at, id"),
                {"preview_id": preview_id},
            ).mappings().all()
        return [self._dict(row) for row in rows]

    def mark_available(
        self,
        artifact_id: str,
        *,
        byte_size: int | None,
        checksum_sha256: str | None,
        status: str = "available",
    ) -> dict[str, Any]:
        with self.engine.begin() as connection:
            updated = connection.execute(
                text(
                    "UPDATE artifact_metadata SET byte_size=:byte_size, checksum_sha256=:checksum, "
                    "status=:status, updated_at=:updated_at WHERE id=:id"
                ),
                {
                    "byte_size": byte_size,
                    "checksum": checksum_sha256,
                    "status": status,
                    "updated_at": utc_now().isoformat(),
                    "id": artifact_id,
                },
            )
            if updated.rowcount != 1:
                raise MetadataNotFound(f"Artifact {artifact_id} was not found")
        return self.get(artifact_id)

    @staticmethod
    def _dict(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "run_id": row.get("run_id"),
            "preview_id": row.get("preview_id"),
            "display_name": row["display_name"],
            "description": row.get("description"),
            "media_type": row["media_type"],
            "byte_size": row.get("byte_size"),
            "status": row["status"],
            "checksum_sha256": row.get("checksum_sha256"),
            "storage_key": row.get("storage_key"),
            "created_at": _timestamp(row.get("created_at")),
            "updated_at": _timestamp(row.get("updated_at")),
        }


__all__ = [
    "ArtifactMetadataRepository",
    "AuditRepository",
    "CalculationRequestRepository",
    "ComparisonRepository",
    "ExportJobRepository",
    "ConfigUpdateResult",
    "DatasetStateRepository",
    "JobEventRepository",
    "MetadataNotFound",
    "PreviewRepository",
    "ProjectRepository",
    "RevisionConflict",
    "RunRepository",
    "ScenarioRepository",
    "StudyAreaRepository",
    "UNSET",
]
