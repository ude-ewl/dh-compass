"""Application services used by the browser API."""

from .configuration import ConfigurationAdapter, ConfigurationChange, ValidatedConfiguration
from .output_discovery import (
    ArtifactRecord,
    DocumentLoad,
    LegacyRun,
    OutputDiscoveryService,
)
from .result_adapter import LegacyResultAdapter
from .startup import (
    FRONTEND_MANIFEST_FILENAME,
    StartupCheck,
    StartupReport,
    run_startup_checks,
)

_LAZY_EXPORTS = {
    "ComparisonInputError",
    "ComparisonService",
    "ExportInputError",
    "ExportService",
    "RetentionService",
}


def __getattr__(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if name in {"ComparisonInputError", "ComparisonService"}:
        from .comparison import ComparisonInputError, ComparisonService

        return {"ComparisonInputError": ComparisonInputError, "ComparisonService": ComparisonService}[name]
    if name in {"ExportInputError", "ExportService", "RetentionService"}:
        from .exports import ExportInputError, ExportService, RetentionService

        return {
            "ExportInputError": ExportInputError,
            "ExportService": ExportService,
            "RetentionService": RetentionService,
        }[name]


__all__ = [
    "ArtifactRecord",
    "ConfigurationAdapter",
    "ConfigurationChange",
    "ValidatedConfiguration",
    "DocumentLoad",
    "LegacyResultAdapter",
    "LegacyRun",
    "OutputDiscoveryService",
    "FRONTEND_MANIFEST_FILENAME",
    "StartupCheck",
    "StartupReport",
    "run_startup_checks",
    "ComparisonInputError",
    "ComparisonService",
    "ExportInputError",
    "ExportService",
    "RetentionService",
]
