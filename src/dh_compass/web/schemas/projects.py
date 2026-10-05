"""Project, scenario, revision, and run-history API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from .base import APIModel, FieldError, Page, PersistedIdentity


class ProjectCreate(APIModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectSummary(PersistedIdentity):
    name: str
    description: str | None = None
    archived: bool = False
    scenario_count: int = Field(default=0, ge=0)
    recent_run_statuses: list[str] = Field(default_factory=list)


class ProjectDetail(ProjectSummary):
    scenarios: list["ScenarioSummary"] = Field(default_factory=list)


ReadinessState = Literal["incomplete", "warning", "complete", "stale", "running"]


class ScenarioCreate(APIModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    source_scenario_id: str | None = None
    document: dict[str, Any] | None = None
    configuration: dict[str, Any] | None = None


class ScenarioUpdate(APIModel):
    expected_revision_id: str
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    archived: bool | None = None


class ScenarioDuplicate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ScenarioRevision(PersistedIdentity):
    scenario_id: str
    parent_revision_id: str | None = None
    revision_number: int = Field(ge=1)
    document: dict[str, Any]


class ScenarioSummary(PersistedIdentity):
    project_id: str
    name: str
    description: str | None = None
    archived: bool = False
    current_revision_id: str | None = None
    revision_number: int = Field(default=0, ge=0)
    readiness_state: ReadinessState = "incomplete"
    preview_id: str | None = None
    preview_stale_reason: str | None = None
    run_required: bool = False
    area_summary: dict[str, Any] = Field(default_factory=dict)
    effective_lhd_threshold: float | None = None
    expert_override_count: int = Field(default=0, ge=0)
    revision: ScenarioRevision | None = None


class ScenarioDetail(ScenarioSummary):
    pass


class ProjectListResponse(Page[ProjectSummary]):
    pass


class ScenarioListResponse(Page[ScenarioSummary]):
    pass


class ScenarioConfigResponse(APIModel):
    scenario_id: str
    revision_id: str
    revision_number: int = Field(ge=1)
    parent_revision_id: str | None = None
    document: dict[str, Any]
    effective_document: dict[str, Any]
    merged_toml: str | None = None
    changed_from_default: list[str] = Field(default_factory=list)
    changed_from_parent: list[str] = Field(default_factory=list)
    created_at: datetime


class ScenarioConfigUpdate(APIModel):
    expected_revision_id: str
    document: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    toml: str | None = None
    # Full-document editors use replacement semantics so deleting an entry
    # from a dynamic cost/technology map is not undone by a deep merge.
    replace: bool = False

    @model_validator(mode="after")
    def _require_document(self) -> "ScenarioConfigUpdate":
        if self.document is None and self.config is None and self.toml is None:
            raise ValueError("document, config, or toml is required")
        return self

    @property
    def submitted_document(self) -> dict[str, Any]:
        return self.document if self.document is not None else self.config or {}


class InvalidationEffects(APIModel):
    effect: Literal["no_downstream_impact", "preview_invalidated", "new_run_required"]
    changed_paths: list[str] = Field(default_factory=list)
    preview_paths: list[str] = Field(default_factory=list)
    run_only_paths: list[str] = Field(default_factory=list)
    no_impact_paths: list[str] = Field(default_factory=list)
    preview_invalidated: bool = False
    new_run_required: bool = False
    run_only_change: bool = False
    reasons: list[str] = Field(default_factory=list)


class ScenarioConfigMutationResponse(APIModel):
    scenario: ScenarioDetail
    revision: ScenarioRevision
    invalidation: InvalidationEffects
    merged_toml: str | None = None
    changed_from_default: list[str] = Field(default_factory=list)
    changed_from_parent: list[str] = Field(default_factory=list)


class ConfigurationValidationResponse(APIModel):
    valid: bool
    document: dict[str, Any] | None = None
    effective_document: dict[str, Any] | None = None
    merged_toml: str | None = None
    changed_paths: list[str] = Field(default_factory=list)
    changed_from_default: list[str] = Field(default_factory=list)
    changed_from_parent: list[str] = Field(default_factory=list)
    invalidation: InvalidationEffects | None = None
    field_errors: list[FieldError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TomlImport(APIModel):
    project_id: str
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    toml: str | None = None
    content: str | None = None

    @model_validator(mode="after")
    def _require_toml(self) -> "TomlImport":
        if self.toml is None and self.content is None:
            raise ValueError("toml or content is required")
        return self

    @property
    def submitted_toml(self) -> str:
        return self.toml if self.toml is not None else self.content or ""


class RunHistory(PersistedIdentity):
    scenario_id: str
    scenario_revision_id: str
    preview_id: str | None = None
    name: str
    description: str | None = None
    status: str
    failure_summary: str | None = None
    warnings: list[Any] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunHistoryListResponse(Page[RunHistory]):
    pass


# Forward references are resolved after both classes have been declared.
ProjectDetail.model_rebuild()


__all__ = [
    "ConfigurationValidationResponse",
    "InvalidationEffects",
    "ProjectCreate",
    "ProjectDetail",
    "ProjectListResponse",
    "ProjectSummary",
    "ProjectUpdate",
    "RunHistory",
    "RunHistoryListResponse",
    "ScenarioConfigMutationResponse",
    "ScenarioConfigResponse",
    "ScenarioConfigUpdate",
    "ScenarioCreate",
    "ScenarioDetail",
    "ScenarioDuplicate",
    "ScenarioListResponse",
    "ScenarioRevision",
    "ScenarioSummary",
    "ScenarioUpdate",
    "TomlImport",
]
