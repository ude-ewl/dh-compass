"""Persistence primitives for web metadata.

Only migration and connection boundaries live here in milestone 0.  Feature
repositories can be added without allowing API handlers to create tables or
open ad-hoc database connections.
"""

from .database import create_metadata_engine
from .identifiers import new_id, new_identifier, now_utc, utc_now
from .migrations import (
    MIGRATIONS,
    Migration,
    MigrationError,
    current_version,
    run_migrations,
)

_REPOSITORY_EXPORTS = {
    "ArtifactMetadataRepository",
    "AuditRepository",
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
}


def __getattr__(name: str):
    if name in _REPOSITORY_EXPORTS:
        from . import repositories

        return getattr(repositories, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "MIGRATIONS",
    "Migration",
    "MigrationError",
    "create_metadata_engine",
    "current_version",
    "new_id",
    "new_identifier",
    "now_utc",
    "run_migrations",
    "utc_now",
    "ArtifactMetadataRepository",
    "AuditRepository",
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
]
