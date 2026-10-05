"""Startup diagnostics for the local DH-COMPASS web application.

The web process is useful even when a full optimization cannot be started: a
user may still inspect completed output folders or fix a missing dataset.  The
checks in this module therefore distinguish *ready*, *degraded*, and
*failed* conditions instead of turning every missing optional resource into a
process crash.  Deployments can opt into strict mode through
:class:`~dh_compass.web.settings.WebSettings`.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping
from uuid import uuid4

from dh_compass import __version__
from dh_compass.config import PathConfig

from ..persistence.migrations import MIGRATIONS
from ..settings import WebSettings

CheckStatus = Literal["ok", "warning", "error"]
ReportStatus = Literal["ready", "degraded", "failed"]

# Keep this filename stable.  It is emitted by the Vite build and is also the
# only frontend file the API needs to inspect for compatibility information.
FRONTEND_MANIFEST_FILENAME = "dh-compass-frontend.json"
FRONTEND_MANIFEST_FILENAMES = (
    FRONTEND_MANIFEST_FILENAME,
    "version.json",  # accepted for deployments that rename the manifest
)


@dataclass(frozen=True, slots=True)
class StartupCheck:
    """One non-sensitive startup check result."""

    name: str
    status: CheckStatus
    message: str
    code: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StartupReport:
    """Serializable startup state retained on ``app.state``."""

    application_version: str
    api_version: str
    migration_version: int | None
    expected_migration_version: int
    frontend_version: str | None
    frontend_api_version: str | None
    checks: tuple[StartupCheck, ...]
    checked_at: datetime

    @property
    def status(self) -> ReportStatus:
        if any(check.status == "error" for check in self.checks):
            return "failed"
        if any(check.status == "warning" for check in self.checks):
            return "degraded"
        return "ready"

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation for logs and diagnostics."""

        return {
            "status": self.status,
            "application_version": self.application_version,
            "api_version": self.api_version,
            "migration_version": self.migration_version,
            "expected_migration_version": self.expected_migration_version,
            "frontend_version": self.frontend_version,
            "frontend_api_version": self.frontend_api_version,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status,
                    "message": check.message,
                    "code": check.code,
                    "details": check.details,
                }
                for check in self.checks
            ],
            "checked_at": self.checked_at.isoformat(),
        }


def run_startup_checks(
    settings: WebSettings,
    *,
    migration_version: int | None,
) -> StartupReport:
    """Run non-destructive checks after database migrations have completed.

    ``migration_version`` is supplied by the application lifespan rather than
    queried here so the check cannot accidentally apply a migration.  This
    keeps migration execution at one explicit startup boundary.
    """

    checks: list[StartupCheck] = []
    expected_migration_version = max((migration.version for migration in MIGRATIONS), default=0)

    if migration_version == expected_migration_version:
        checks.append(
            StartupCheck(
                name="database_migrations",
                status="ok",
                code="DATABASE_MIGRATIONS_CURRENT",
                message=f"Metadata database is at migration {migration_version}.",
                details={
                    "current_version": migration_version,
                    "expected_version": expected_migration_version,
                },
            )
        )
    else:
        checks.append(
            StartupCheck(
                name="database_migrations",
                status="error",
                code="DATABASE_MIGRATIONS_OUT_OF_DATE",
                message="The metadata database is not at the application migration version.",
                details={
                    "current_version": migration_version,
                    "expected_version": expected_migration_version,
                },
            )
        )

    paths = PathConfig.from_project_root(settings.project_root)
    # Check the roots before creating cache/output directories.  Otherwise a
    # missing ``data`` directory would be accidentally made to look healthy by
    # the cache permission probe below.
    checks.extend(
        _data_root_checks(
            (
                ("data_root", paths.data_root),
                ("reference_data", paths.reference_data),
                ("external_data", paths.external_data),
                ("examples_data", paths.examples_data),
            )
        )
    )
    checks.extend(
        (
            _writable_directory_check("output_root", Path(settings.output_root)),
            _writable_directory_check("cache_root", paths.cache_root),
            _writable_directory_check(
                "metadata_database_parent", _database_parent(settings.metadata_database_path)
            ),
        )
    )
    checks.append(_solver_check())

    frontend_check, frontend_version, frontend_api_version = _frontend_check(
        settings.frontend_static_path
    )
    checks.append(frontend_check)

    if settings.strict_startup_checks:
        checks = [_strictify(check) for check in checks]

    return StartupReport(
        application_version=__version__,
        api_version=__version__,
        migration_version=migration_version,
        expected_migration_version=expected_migration_version,
        frontend_version=frontend_version,
        frontend_api_version=frontend_api_version,
        checks=tuple(checks),
        checked_at=datetime.now(timezone.utc),
    )


def _strictify(check: StartupCheck) -> StartupCheck:
    if check.status != "warning":
        return check
    return StartupCheck(
        name=check.name,
        status="error",
        code=check.code,
        message=check.message,
        details={**check.details, "strict_mode": True},
    )


def _database_parent(value: Path | str) -> Path | None:
    if isinstance(value, str) and value == ":memory:":
        return None
    return Path(value).expanduser().resolve().parent


def _writable_directory_check(name: str, path: Path | None) -> StartupCheck:
    if path is None:
        return StartupCheck(
            name=name,
            status="ok",
            code="PATH_NOT_APPLICABLE",
            message="No filesystem directory is required for this setting.",
        )

    try:
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            raise OSError("configured path is not a directory")
        # A real create/delete probe catches permissions on platforms where
        # os.access() reports the process account inaccurately (notably Windows
        # and network-mounted directories).
        probe = path / f".dh-compass-startup-{uuid4().hex}"
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as exc:
        return StartupCheck(
            name=name,
            status="error",
            code="PATH_NOT_WRITABLE",
            message=f"{name.replace('_', ' ').capitalize()} is not writable.",
            details={"path": str(path), "error": str(exc)},
        )
    return StartupCheck(
        name=name,
        status="ok",
        code="PATH_WRITABLE",
        message=f"{name.replace('_', ' ').capitalize()} is writable.",
        details={"path": str(path)},
    )


def _data_root_checks(roots: tuple[tuple[str, Path], ...]) -> list[StartupCheck]:
    result: list[StartupCheck] = []
    for name, path in roots:
        try:
            available = path.is_dir()
            if available:
                # Opening the iterator verifies that the process can inspect
                # the root without enumerating potentially large datasets.
                iterator = path.iterdir()
                next(iterator, None)
        except OSError as exc:
            available = False
            error = str(exc)
        else:
            error = None
        if available:
            result.append(
                StartupCheck(
                    name=name,
                    status="ok",
                    code="DATA_ROOT_AVAILABLE",
                    message=f"Required data root {name} is available.",
                    details={"path": str(path)},
                )
            )
        else:
            result.append(
                StartupCheck(
                    name=name,
                    status="warning",
                    code="DATA_ROOT_MISSING",
                    message=(
                        f"Required data root {name} is not available; scenario runs may be unavailable."
                    ),
                    details={"path": str(path), **({"error": error} if error else {})},
                )
            )
    return result


def _solver_check() -> StartupCheck:
    try:
        spec = importlib.util.find_spec("mip")
    except (ImportError, ModuleNotFoundError, ValueError) as exc:
        spec = None
        error = str(exc)
    else:
        error = None
    if spec is None:
        return StartupCheck(
            name="solver",
            status="warning",
            code="SOLVER_UNAVAILABLE",
            message="The python-mip solver package is not available; new runs cannot start.",
            details={"package": "mip", **({"error": error} if error else {})},
        )
    try:
        module = importlib.import_module("mip")
        version = str(getattr(module, "__version__", "unknown"))
    except Exception as exc:  # noqa: BLE001 - diagnostics must not stop read-only mode
        return StartupCheck(
            name="solver",
            status="warning",
            code="SOLVER_IMPORT_FAILED",
            message="The python-mip solver package could not be imported; new runs may fail.",
            details={"package": "mip", "error": str(exc)},
        )
    return StartupCheck(
        name="solver",
        status="ok",
        code="SOLVER_AVAILABLE",
        message="The python-mip solver package is available.",
        details={"package": "mip", "version": version},
    )


def _frontend_check(
    static_path: Path | str | None,
) -> tuple[StartupCheck, str | None, str | None]:
    path = Path(static_path).expanduser().resolve() if static_path is not None else None
    if path is None or not path.is_dir():
        return (
            StartupCheck(
                name="frontend_assets",
                status="warning",
                code="FRONTEND_ASSETS_MISSING",
                message="Compiled frontend assets are not installed; the API remains available.",
                details={"path": str(path) if path is not None else None},
            ),
            None,
            None,
        )

    index_path = path / "index.html"
    if not index_path.is_file():
        return (
            StartupCheck(
                name="frontend_assets",
                status="error",
                code="FRONTEND_INDEX_MISSING",
                message="The configured frontend directory does not contain index.html.",
                details={"path": str(path)},
            ),
            None,
            None,
        )

    manifest_path = next(
        (path / filename for filename in FRONTEND_MANIFEST_FILENAMES if (path / filename).is_file()),
        None,
    )
    if manifest_path is None:
        return (
            StartupCheck(
                name="frontend_assets",
                status="warning",
                code="FRONTEND_VERSION_MANIFEST_MISSING",
                message=(
                    "Frontend assets are present but have no compatibility manifest; rebuild the frontend "
                    "before packaging it."
                ),
                details={"path": str(path), "expected_manifest": FRONTEND_MANIFEST_FILENAME},
            ),
            None,
            None,
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (
            StartupCheck(
                name="frontend_assets",
                status="error",
                code="FRONTEND_VERSION_MANIFEST_INVALID",
                message="The frontend compatibility manifest cannot be read.",
                details={"path": str(manifest_path), "error": str(exc)},
            ),
            None,
            None,
        )
    if not isinstance(manifest, Mapping):
        return (
            StartupCheck(
                name="frontend_assets",
                status="error",
                code="FRONTEND_VERSION_MANIFEST_INVALID",
                message="The frontend compatibility manifest must contain a JSON object.",
                details={"path": str(manifest_path)},
            ),
            None,
            None,
        )

    application = manifest.get("application")
    frontend_version = _string_or_none(
        manifest.get("frontend_version") or manifest.get("version")
    )
    frontend_api_version = _string_or_none(
        manifest.get("api_version") or manifest.get("api") or manifest.get("version")
    )
    if application not in {None, "dh-compass"}:
        return (
            StartupCheck(
                name="frontend_assets",
                status="error",
                code="FRONTEND_APPLICATION_MISMATCH",
                message="The frontend assets belong to a different application.",
                details={"application": application, "expected": "dh-compass"},
            ),
            frontend_version,
            frontend_api_version,
        )
    if frontend_api_version != __version__:
        return (
            StartupCheck(
                name="frontend_assets",
                status="error",
                code="FRONTEND_API_VERSION_MISMATCH",
                message="The compiled frontend and API versions are incompatible.",
                details={
                    "frontend_api_version": frontend_api_version,
                    "api_version": __version__,
                    "manifest": str(manifest_path),
                },
            ),
            frontend_version,
            frontend_api_version,
        )
    return (
        StartupCheck(
            name="frontend_assets",
            status="ok",
            code="FRONTEND_VERSION_COMPATIBLE",
            message="Compiled frontend assets are compatible with the API.",
            details={
                "path": str(path),
                "manifest": str(manifest_path),
                "frontend_version": frontend_version,
                "api_version": frontend_api_version,
            },
        ),
        frontend_version,
        frontend_api_version,
    )


def _string_or_none(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = [
    "CheckStatus",
    "FRONTEND_MANIFEST_FILENAME",
    "FRONTEND_MANIFEST_FILENAMES",
    "ReportStatus",
    "StartupCheck",
    "StartupReport",
    "run_startup_checks",
]
