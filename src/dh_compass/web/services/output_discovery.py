"""Discovery and safe access to legacy DH-COMPASS output folders.

The service is intentionally read-only.  It treats ``output_root`` as the only
filesystem boundary and never accepts an arbitrary path from an API caller.
Legacy runs are discovered from the existing ``outputs/<scenario>/<timestamp>``
layout so the browser can be introduced without changing the CLI pipeline.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from ..schemas.results import ArtifactAvailability, RunManifest

_KNOWN_ARTIFACTS: tuple[tuple[str, str, str, str], ...] = (
    ("full_results.json", "Full results", "results", "application/json"),
    ("viewer_data.json", "Decision playback data", "viewer", "application/json"),
    ("performance_metrics.json", "Performance metrics", "diagnostics", "application/json"),
    ("final_network.geojson", "Final network", "map", "application/geo+json"),
    ("lhd_graph.geojson", "Linear heat density graph", "map", "application/geo+json"),
    ("viewer_data.html", "Deprecated standalone viewer (compatibility fallback)", "viewer", "text/html"),
    ("chart_capacity.png", "Supply capacity chart", "chart", "image/png"),
    ("chart_energy_shares.png", "Supply energy shares chart", "chart", "image/png"),
    ("chart_cost_structure.png", "Cost structure chart", "chart", "image/png"),
    ("chart_cost_detailed.png", "Detailed grid cost chart", "chart", "image/png"),
    ("chart_cost_pie.png", "Total cost breakdown chart", "chart", "image/png"),
    # Time-series exports are optional and are intentionally listed explicitly
    # so a caller can never use the browser API to read an arbitrary file.
    ("timeseries.json", "Time-series data", "timeseries", "application/json"),
    ("time_series.json", "Time-series data", "timeseries", "application/json"),
    ("results_timeseries.json", "Time-series data", "timeseries", "application/json"),
    ("timeseries.csv", "Time-series data", "timeseries", "text/csv"),
    ("time_series.csv", "Time-series data", "timeseries", "text/csv"),
)


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """An artifact record with an internal path kept out of API responses."""

    id: str
    display_name: str
    kind: str
    media_type: str
    status: str
    path: Path | None
    byte_size: int | None = None
    checksum_sha256: str | None = None
    error: str | None = None

    def to_schema(self, *, download_url: str | None = None) -> ArtifactAvailability:
        return ArtifactAvailability(
            id=self.id,
            display_name=self.display_name,
            kind=self.kind,
            media_type=self.media_type,
            status=self.status,  # type: ignore[arg-type]
            available=self.status == "available",
            byte_size=self.byte_size,
            checksum_sha256=self.checksum_sha256,
            error=self.error,
            download_url=download_url,
        )


@dataclass(frozen=True, slots=True)
class DocumentLoad:
    """Result of reading one JSON artifact without conflating missing and invalid."""

    status: str
    value: Any | None = None
    artifact: ArtifactRecord | None = None
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.status == "available"


@dataclass(frozen=True, slots=True)
class LegacyRun:
    """Internal representation of one discovered output directory."""

    id: str
    scenario: str
    timestamp: str
    path: Path
    created_at: datetime
    updated_at: datetime
    artifacts: tuple[ArtifactRecord, ...]
    summary: dict[str, Any] | None
    warnings: tuple[str, ...]

    @property
    def status(self) -> str:
        available_documents = {
            artifact.id
            for artifact in self.artifacts
            if artifact.status == "available"
        }
        return "completed" if {"full_results.json", "viewer_data.json"} & available_documents else "incomplete"

    def artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return next((item for item in self.artifacts if item.id == artifact_id), None)

    def to_schema(self, *, download_url_for=None) -> RunManifest:
        artifacts = [
            artifact.to_schema(
                download_url=(
                    download_url_for(self.id, artifact.id)
                    if download_url_for and artifact.status == "available"
                    else None
                )
            )
            for artifact in self.artifacts
        ]
        return RunManifest(
            id=self.id,
            scenario=self.scenario,
            timestamp=self.timestamp,
            display_name=f"{self.scenario} — {self.timestamp}",
            status=self.status,  # type: ignore[arg-type]
            source="legacy_output",
            legacy=True,
            created_at=self.created_at,
            updated_at=self.updated_at,
            summary=self.summary,
            artifacts=artifacts,
            warnings=list(self.warnings),
        )


class OutputDiscoveryService:
    """Scan and read legacy output directories below one configured root."""

    def __init__(self, output_root: str | Path):
        self.output_root = Path(output_root).expanduser().resolve()

    def list_runs(self) -> list[RunManifest]:
        """Return discovered runs, newest first, without raising for bad artifacts."""

        return [
            run.to_schema()
            for run in sorted(
                (self._inspect_run(path) for path in self._iter_run_paths()),
                key=lambda item: (item.updated_at, item.id),
                reverse=True,
            )
        ]

    def get_run(self, run_id: str) -> RunManifest:
        return self._get_legacy_run(run_id).to_schema()

    def get_legacy_run(self, run_id: str) -> LegacyRun:
        """Return the internal run record for result adapters and download routes."""

        return self._get_legacy_run(run_id)

    def load_json(self, run_id: str, artifact_id: str) -> DocumentLoad:
        """Read a JSON artifact and preserve missing/invalid status information."""

        run = self._get_legacy_run(run_id)
        artifact = run.artifact(unquote(artifact_id))
        if artifact is None:
            return DocumentLoad(status="missing", error="Artifact was not found.")
        if artifact.status == "missing":
            return DocumentLoad(status="missing", artifact=artifact, error=artifact.error)
        if artifact.status == "invalid":
            return DocumentLoad(status="invalid", artifact=artifact, error=artifact.error)
        if artifact.path is None:
            return DocumentLoad(status="missing", artifact=artifact, error="Artifact is not present.")
        try:
            with artifact.path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return DocumentLoad(
                status="invalid",
                artifact=artifact,
                error=f"Could not read {artifact.id}: {exc}",
            )
        return DocumentLoad(status="available", value=value, artifact=artifact)

    def resolve_artifact(self, run_id: str, artifact_id: str) -> Path:
        """Resolve a known artifact while rejecting traversal and symlink escapes."""

        run = self._get_legacy_run(run_id)
        normalized_id = unquote(artifact_id).replace("\\", "/")
        artifact = run.artifact(normalized_id)
        if artifact is None or artifact.status != "available" or artifact.path is None:
            raise FileNotFoundError("Artifact was not found")
        candidate = artifact.path
        if _has_symlink_component(candidate, run.path):
            raise FileNotFoundError("Artifact was not found")
        path = candidate.resolve()
        if not _is_relative_to(path, run.path) or not _is_relative_to(path, self.output_root):
            raise FileNotFoundError("Artifact was not found")
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError("Artifact was not found")
        return path

    def _iter_run_paths(self):
        if not self.output_root.is_dir() or self.output_root.is_symlink():
            return
        try:
            scenario_paths = sorted(self.output_root.iterdir(), key=lambda path: path.name)
        except OSError:
            return
        for scenario_path in scenario_paths:
            if (
                not scenario_path.is_dir()
                or scenario_path.is_symlink()
                or scenario_path.name.startswith(".")
            ):
                continue
            try:
                run_paths = sorted(scenario_path.iterdir(), key=lambda path: path.name)
            except OSError:
                continue
            for run_path in run_paths:
                if (
                    run_path.is_dir()
                    and not run_path.is_symlink()
                    and not run_path.name.startswith(".")
                    and _is_relative_to(run_path.resolve(), self.output_root)
                ):
                    yield run_path

    def _get_legacy_run(self, run_id: str) -> LegacyRun:
        normalized = unquote(str(run_id)).replace("\\", "/")
        if not normalized or "\x00" in normalized:
            raise FileNotFoundError("Run was not found")
        candidate = Path(normalized)
        if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
            raise FileNotFoundError("Run was not found")
        path = (self.output_root / Path(*candidate.parts)).resolve()
        if not _is_relative_to(path, self.output_root) or not path.is_dir() or path.is_symlink():
            raise FileNotFoundError("Run was not found")
        # Only the two-level legacy layout is discoverable.  This also prevents
        # a caller from selecting an arbitrary nested directory under outputs.
        relative = path.relative_to(self.output_root)
        if len(relative.parts) != 2:
            raise FileNotFoundError("Run was not found")
        if path not in set(self._iter_run_paths()):
            raise FileNotFoundError("Run was not found")
        return self._inspect_run(path)

    def _inspect_run(self, path: Path) -> LegacyRun:
        relative = path.relative_to(self.output_root)
        run_id = relative.as_posix()
        created_at = _file_time(path, "created")
        updated_at = _file_time(path, "modified")
        artifacts, warnings = self._inspect_artifacts(path)
        summary = self._summary_from_artifacts(path, artifacts)
        return LegacyRun(
            id=run_id,
            scenario=relative.parts[0],
            timestamp=relative.parts[1],
            path=path,
            created_at=created_at,
            updated_at=updated_at,
            artifacts=tuple(artifacts),
            summary=summary,
            warnings=tuple(warnings),
        )

    def _inspect_artifacts(self, path: Path) -> tuple[list[ArtifactRecord], list[str]]:
        records: dict[str, ArtifactRecord] = {}
        warnings: list[str] = []

        known = {name: (display, kind, media_type) for name, display, kind, media_type in _KNOWN_ARTIFACTS}
        for name, (display_name, kind, media_type) in known.items():
            file_path = path / name
            records[name] = self._artifact_record(
                path,
                name,
                display_name,
                kind,
                media_type,
                expected=True,
            )

        try:
            files = sorted(
                (item for item in path.rglob("*") if item.is_file() and not item.is_symlink()),
                key=lambda item: item.relative_to(path).as_posix(),
            )
        except OSError:
            files = []
        for file_path in files:
            relative_id = file_path.relative_to(path).as_posix()
            if relative_id in records:
                continue
            records[relative_id] = self._artifact_record(
                path,
                relative_id,
                file_path.name,
                _kind_for(file_path),
                _media_type_for(file_path),
                expected=False,
            )

        result = list(records.values())
        for artifact in result:
            if artifact.status == "invalid":
                warnings.append(f"{artifact.display_name} is malformed: {artifact.error}")
        return result, warnings

    def _artifact_record(
        self,
        run_path: Path,
        artifact_id: str,
        display_name: str,
        kind: str,
        media_type: str,
        *,
        expected: bool,
    ) -> ArtifactRecord:
        path = run_path / Path(*artifact_id.split("/"))
        if not _is_relative_to(path.resolve(strict=False), run_path):
            return ArtifactRecord(
                artifact_id,
                display_name,
                kind,
                media_type,
                "invalid",
                None,
                error="Artifact path is outside the run directory.",
            )
        if not path.exists() or not path.is_file():
            return ArtifactRecord(
                artifact_id,
                display_name,
                kind,
                media_type,
                "missing",
                None,
                error="Artifact is not present.",
            )
        if _has_symlink_component(path, run_path) or not _is_relative_to(path.resolve(), self.output_root):
            return ArtifactRecord(
                artifact_id,
                display_name,
                kind,
                media_type,
                "invalid",
                None,
                error="Artifact resolves outside the configured output root.",
            )

        error = None
        status = "available"
        if path.suffix.lower() in {".json", ".geojson"}:
            try:
                with path.open("r", encoding="utf-8") as handle:
                    document = json.load(handle)
                if path.suffix.lower() == ".geojson" and not isinstance(document, dict):
                    raise ValueError("GeoJSON document must be an object")
                if path.name in {
                    "full_results.json",
                    "viewer_data.json",
                    "performance_metrics.json",
                } and not isinstance(document, dict):
                    raise ValueError("JSON result document must be an object")
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                status = "invalid"
                error = str(exc)
        try:
            byte_size = path.stat().st_size
        except OSError:
            byte_size = None
        checksum = _sha256(path) if status == "available" else None
        return ArtifactRecord(
            artifact_id,
            display_name,
            kind,
            media_type,
            status,
            path,
            byte_size,
            checksum,
            error,
        )

    def _summary_from_artifacts(
        self, path: Path, artifacts: list[ArtifactRecord]
    ) -> dict[str, Any] | None:
        for artifact_id in ("full_results.json", "viewer_data.json"):
            artifact = next(item for item in artifacts if item.id == artifact_id)
            if artifact.status != "available" or artifact.path is None:
                continue
            try:
                with artifact.path.open("r", encoding="utf-8") as handle:
                    document = json.load(handle)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            summary = _enrich_summary(document)
            if summary is not None:
                return summary
        return None


def _enrich_summary(document: Any) -> dict[str, Any] | None:
    if not isinstance(document, Mapping) or not isinstance(document.get("summary"), Mapping):
        return None
    result = dict(document["summary"])
    combined = document.get("combined_graph")
    if isinstance(combined, Mapping):
        field_map = {
            "connected_buildings": "total_buildings",
            "total_network_length_m": "total_network_length_m",
            "peak_load_kw": "peak_load_kw",
            "connected_heat_demand_mwh": "annual_heat_demand_mwh",
        }
        for target, source in field_map.items():
            if source in combined:
                result[target] = combined[source]
        network_length = combined.get("total_network_length_m")
        connection_length = combined.get("connection_length_m")
        if isinstance(network_length, (int, float)) and isinstance(connection_length, (int, float)):
            length = network_length + connection_length
            result["final_connection_length_m"] = length
            demand = result.get("connected_heat_demand_mwh")
            if isinstance(demand, (int, float)) and length > 0:
                result["average_linear_heat_density_mwh_per_m_a"] = demand / length
        cost = combined.get("cost")
        if isinstance(cost, Mapping):
            for target, source in (
                ("total_annualized_eur", "total_annualized_eur"),
                ("supply_annualized_eur", "supply_annualized_eur"),
                ("grid_annualized_eur", "grid_annualized_eur"),
            ):
                if source in cost:
                    result[target] = cost[source]
    return result


def _has_symlink_component(path: Path, parent: Path) -> bool:
    """Return whether ``path`` or a child path component is a symlink."""

    current = path
    while True:
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
        if current == parent:
            return False
        next_parent = current.parent
        if next_parent == current:
            return True
        current = next_parent


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _file_time(path: Path, mode: str) -> datetime:
    try:
        stat = path.stat()
        value = stat.st_ctime if mode == "created" else stat.st_mtime
    except OSError:
        value = 0
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _kind_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".geojson", ".gpkg", ".shp"}:
        return "map"
    if suffix in {".png", ".svg", ".jpg", ".jpeg", ".pdf"}:
        return "chart"
    if path.name.endswith(".html"):
        return "viewer"
    if suffix == ".json":
        return "results"
    if suffix in {".csv", ".xlsx"}:
        return "data"
    return "artifact"


def _media_type_for(path: Path) -> str:
    if path.suffix.lower() == ".geojson":
        return "application/geo+json"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


__all__ = [
    "ArtifactRecord",
    "DocumentLoad",
    "LegacyRun",
    "OutputDiscoveryService",
]
