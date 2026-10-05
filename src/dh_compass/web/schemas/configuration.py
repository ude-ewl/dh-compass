"""Configuration metadata schemas used by standard and Expert settings."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .base import APIModel

ConfigurationDataType = Literal[
    "boolean",
    "integer",
    "number",
    "string",
    "array",
    "object",
    "unknown",
]
ConfigurationImpact = Literal["none", "preview", "run"]


class ConfigurationField(APIModel):
    key: str
    section: str
    section_label: str
    # ``group`` is a presentation grouping.  ``section`` remains the canonical
    # configuration-document section and is therefore stable for clients that
    # use the field key programmatically.
    group: str | None = None
    group_label: str | None = None
    label: str
    description: str
    data_type: ConfigurationDataType
    unit: str | None = None
    default: Any = None
    has_default: bool = True
    value: Any = None
    parent_value: Any = None
    changed_from_default: bool = False
    changed_from_parent: bool = False
    expert_only: bool
    editable: bool = True
    runtime_only: bool = False
    impact: ConfigurationImpact
    preprocessing_impact: bool
    sensitive: bool = False
    path_policy: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)


class ConfigurationSchemaResponse(APIModel):
    version: str
    fields: list[ConfigurationField]
    scenario_id: str | None = None
    revision_id: str | None = None
    parent_revision_id: str | None = None


__all__ = [
    "ConfigurationDataType",
    "ConfigurationField",
    "ConfigurationImpact",
    "ConfigurationSchemaResponse",
]
