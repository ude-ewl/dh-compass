"""Explicit settings for the local web application.

The web process has a smaller path surface than a model run, but it still must
not derive paths from the process working directory.  Defaults come from the
same :class:`~dh_compass.config.PathConfig` used by the command line
application; deployment-specific values can be supplied explicitly or through
the documented environment variables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from os import environ
from pathlib import Path
from typing import Mapping

from dh_compass.config import PathConfig

_DEFAULT_DATABASE_NAME = "dh-compass-web.sqlite3"
_DEFAULT_GEOCODING_ENDPOINT = "https://nominatim.openstreetmap.org/search"


def _project_root(value: str | Path | None) -> Path:
    return PathConfig.from_project_root(value).project_root


def _resolve_path(value: str | Path, root: Path) -> Path | str:
    """Resolve a configured path without consulting the current directory."""

    if isinstance(value, str) and value == ":memory:":
        # Useful for isolated tests and deliberately not a filesystem path.
        return value
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _parse_origins(value: str | tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(origin.strip() for origin in value.split(",") if origin.strip())
    return tuple(origin.strip() for origin in value if origin.strip())


@dataclass(frozen=True, slots=True)
class WebSettings:
    """Runtime settings owned by the FastAPI application.

    ``metadata_database_path`` and ``output_root`` may be relative when passed
    by a caller.  They are resolved against ``project_root`` during
    construction, so the rest of the web package only handles absolute paths.
    """

    metadata_database_path: Path | str = field(default="")
    output_root: Path | str | None = None
    worker_concurrency: int = 1
    frontend_static_path: Path | str | None = None
    development_cors_origins: tuple[str, ...] = ()
    artifact_retention_days: int = 30
    geocoding_endpoint: str | None = _DEFAULT_GEOCODING_ENDPOINT
    frontend_redesign_enabled: bool = True
    project_root: Path | str = field(default_factory=lambda: PathConfig.from_project_root().project_root)
    strict_startup_checks: bool = False

    def __post_init__(self) -> None:
        root = _project_root(self.project_root)
        paths = PathConfig.from_project_root(root)

        database_value: Path | str = self.metadata_database_path
        if database_value == "":
            database_value = paths.cache_root / _DEFAULT_DATABASE_NAME
        database = _resolve_path(database_value, root)

        output_value = self.output_root if self.output_root is not None else paths.output_root
        output = _resolve_path(output_value, root)

        if self.frontend_static_path is not None:
            static_value: Path | str = self.frontend_static_path
        else:
            source_build = root / "frontend" / "dist"
            packaged_build = Path(__file__).resolve().parent / "static"
            # A release job may copy the Vite output into package data.  The
            # repository build remains the default whenever it exists; this
            # fallback makes the same API work from a wheel without requiring
            # a repository checkout as the process root.
            static_value = (
                source_build
                if (source_build / "index.html").is_file()
                else packaged_build
            )
        static = _resolve_path(static_value, root)

        if self.worker_concurrency < 1:
            raise ValueError("worker_concurrency must be at least 1")
        if self.artifact_retention_days < 0:
            raise ValueError("artifact_retention_days must be nonnegative")

        object.__setattr__(self, "project_root", root)
        object.__setattr__(self, "metadata_database_path", database)
        object.__setattr__(self, "output_root", output)
        object.__setattr__(self, "frontend_static_path", static)
        object.__setattr__(self, "development_cors_origins", _parse_origins(self.development_cors_origins))
        if self.geocoding_endpoint is not None:
            object.__setattr__(self, "geocoding_endpoint", self.geocoding_endpoint.strip() or None)

    @property
    def database_path(self) -> Path | str:
        """Backward-compatible short name for the metadata database path."""

        return self.metadata_database_path

    @property
    def metadata_db_path(self) -> Path | str:
        """Concise alias used by deployment integrations."""

        return self.metadata_database_path

    @property
    def cors_origins(self) -> tuple[str, ...]:
        """Configured development origins, exposed with a concise API name."""

        return self.development_cors_origins

    @classmethod
    def from_path_config(
        cls,
        paths: PathConfig,
        *,
        metadata_database_path: str | Path | None = None,
        output_root: str | Path | None = None,
        worker_concurrency: int = 1,
        frontend_static_path: str | Path | None = None,
        development_cors_origins: tuple[str, ...] | list[str] | str = (),
        geocoding_endpoint: str | None = _DEFAULT_GEOCODING_ENDPOINT,
        frontend_redesign_enabled: bool = True,
        artifact_retention_days: int = 30,
        strict_startup_checks: bool = False,
    ) -> "WebSettings":
        """Build web settings from the canonical application path config."""

        return cls(
            project_root=paths.project_root,
            metadata_database_path=(
                metadata_database_path
                if metadata_database_path is not None
                else paths.cache_root / _DEFAULT_DATABASE_NAME
            ),
            output_root=output_root if output_root is not None else paths.output_root,
            worker_concurrency=worker_concurrency,
            frontend_static_path=frontend_static_path,
            development_cors_origins=_parse_origins(development_cors_origins),
            geocoding_endpoint=geocoding_endpoint,
            frontend_redesign_enabled=frontend_redesign_enabled,
            artifact_retention_days=artifact_retention_days,
            strict_startup_checks=strict_startup_checks,
        )

    @classmethod
    def from_env(
        cls,
        values: Mapping[str, str] | None = None,
        *,
        project_root: str | Path | None = None,
    ) -> "WebSettings":
        """Alias for :meth:`from_environment`."""

        return cls.from_environment(values, project_root=project_root)

    @classmethod
    def from_environment(
        cls,
        values: Mapping[str, str] | None = None,
        *,
        project_root: str | Path | None = None,
    ) -> "WebSettings":
        """Read deployment settings from environment-like values.

        The optional ``values`` argument keeps this method deterministic in
        tests and avoids mutating process-global environment state.
        """

        environment = environ if values is None else values
        root_value = project_root or environment.get("DH_COMPASS_PROJECT_ROOT")
        paths = PathConfig.from_project_root(root_value)

        def optional_path(name: str) -> str | None:
            value = environment.get(name)
            return value.strip() if value and value.strip() else None

        concurrency_value = environment.get("DH_COMPASS_WEB_WORKER_CONCURRENCY", "1")
        try:
            concurrency = int(concurrency_value)
        except ValueError as exc:
            raise ValueError("DH_COMPASS_WEB_WORKER_CONCURRENCY must be an integer") from exc

        retention_value = environment.get("DH_COMPASS_WEB_ARTIFACT_RETENTION_DAYS", "30")
        try:
            artifact_retention_days = int(retention_value)
        except ValueError as exc:
            raise ValueError(
                "DH_COMPASS_WEB_ARTIFACT_RETENTION_DAYS must be an integer"
            ) from exc

        strict_value = environment.get("DH_COMPASS_WEB_STRICT_STARTUP_CHECKS", "0")
        strict_startup_checks = strict_value.strip().lower() in {"1", "true", "yes", "on"}
        redesign_value = environment.get(
            "DH_COMPASS_WEB_FRONTEND_REDESIGN",
            environment.get("DH_COMPASS_FRONTEND_REDESIGN", "1"),
        )
        frontend_redesign_enabled = redesign_value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        return cls.from_path_config(
            paths,
            metadata_database_path=optional_path("DH_COMPASS_WEB_DATABASE_PATH"),
            output_root=optional_path("DH_COMPASS_WEB_OUTPUT_ROOT"),
            worker_concurrency=concurrency,
            frontend_static_path=optional_path("DH_COMPASS_WEB_FRONTEND_STATIC_PATH"),
            development_cors_origins=environment.get("DH_COMPASS_WEB_CORS_ORIGINS", ""),
            geocoding_endpoint=(
                environment.get(
                    "DH_COMPASS_WEB_GEOCODING_ENDPOINT",
                    _DEFAULT_GEOCODING_ENDPOINT,
                ).strip()
                or None
            ),
            frontend_redesign_enabled=frontend_redesign_enabled,
            artifact_retention_days=artifact_retention_days,
            strict_startup_checks=strict_startup_checks,
        )


__all__ = ["WebSettings"]
