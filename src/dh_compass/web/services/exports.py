"""Safe CSV, printable-report, and reproducibility-bundle exports."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
import zipfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from dh_compass import __version__
from dh_compass.web.persistence.repositories import (
    ExportJobRepository,
    MetadataNotFound,
    RunRepository,
)
from dh_compass.web.services.configuration import ConfigurationAdapter
from dh_compass.web.services.output_discovery import LegacyRun, OutputDiscoveryService
from dh_compass.web.services.result_adapter import LegacyResultAdapter


class ExportInputError(ValueError):
    """Raised when an export cannot be produced from a completed run."""


_ALLOWED_TABLES = {
    "summary",
    "candidates",
    "iterations",
    "supply",
    "costs",
    "decentral",
}
_TABLE_ALIASES = {
    "candidate": "candidates",
    "iteration": "iterations",
    "supply_portfolio": "supply",
    "cost": "costs",
    "decentralized": "decentral",
}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
# Keep this explicit: adding a new reproducibility artifact is a conscious
# contract and security decision rather than an implicit directory sweep.
_BUNDLE_ARTIFACT_IDS = (
    "run_manifest.json",
    "full_results.json",
    "viewer_data.json",
    "performance_metrics.json",
    "final_network.geojson",
    "lhd_graph.geojson",
    "timeseries.json",
    "time_series.json",
    "results_timeseries.json",
    "timeseries.csv",
    "time_series.csv",
    "run.log",
)


class ExportService:
    """Generate exports below a managed root and return durable job records."""

    def __init__(
        self,
        discovery: OutputDiscoveryService,
        *,
        output_root: str | Path,
        project_root: str | Path,
        engine: Engine,
    ):
        self.discovery = discovery
        self.output_root = Path(output_root).expanduser().resolve()
        self.project_root = Path(project_root).expanduser().resolve()
        self.engine = engine
        self.adapter = LegacyResultAdapter(discovery)

    def enqueue(
        self,
        run_id: str,
        kind: str,
        *,
        table: str | None = None,
    ) -> dict[str, Any]:
        """Validate and persist an export request without doing file I/O.

        Generation is deliberately separated so API handlers can return the
        durable queued job before a potentially large bundle is read.
        """

        legacy, _ = self._resolve_completed_run(run_id)
        if kind == "csv":
            normalized_table = self.normalize_table(
                table.strip() if isinstance(table, str) and table.strip() else "summary"
            )
            display_name = f"{normalized_table}-{_safe_component(run_id)}.csv"
            media_type = "text/csv"
        elif kind == "report":
            normalized_table = None
            display_name = f"{_safe_component(legacy.scenario)}-report.html"
            media_type = "text/html"
        elif kind == "bundle":
            normalized_table = None
            display_name = f"{_safe_component(legacy.scenario)}-reproducibility.zip"
            media_type = "application/zip"
        else:
            raise ExportInputError(f"Unsupported export kind: {kind}")
        return ExportJobRepository(self.engine).create(
            run_id,
            kind,
            display_name=display_name,
            media_type=media_type,
            metadata={"table": normalized_table} if normalized_table else {},
        )

    def generate(self, export_id: str) -> dict[str, Any]:
        """Generate one previously queued export outside the request path."""

        jobs = ExportJobRepository(self.engine)
        job = jobs.get(export_id)
        if job["status"] in {"available", "failed"}:
            return job
        try:
            job = jobs.update(export_id, "running")
            legacy, managed = self._resolve_completed_run(str(job["run_id"]))
            export_dir = self.output_root / ".web_exports" / export_id
            output_path = export_dir / str(job["display_name"])
            export_dir.mkdir(parents=True, exist_ok=True)
            if job["kind"] == "csv":
                content = self.csv_bytes(
                    legacy.id, str(job.get("metadata", {}).get("table") or "summary")
                )
                output_path.write_bytes(content)
            elif job["kind"] == "report":
                output_path.write_text(self._report_html(legacy, managed), encoding="utf-8")
            elif job["kind"] == "bundle":
                output_path.write_bytes(self._bundle_bytes(legacy, managed))
            else:
                raise ExportInputError(f"Unsupported export kind: {job['kind']}")
            return jobs.update(
                export_id,
                "available",
                storage_key=output_path.relative_to(self.output_root).as_posix(),
                byte_size=output_path.stat().st_size,
                checksum_sha256=_sha256(output_path),
            )
        except Exception as exc:
            jobs.update(export_id, "failed", error=str(exc))
            return jobs.get(export_id)

    def get_path(self, job: Mapping[str, Any]) -> Path:
        storage_key = job.get("storage_key")
        if not isinstance(storage_key, str) or not storage_key:
            raise FileNotFoundError("Export is not available")
        root = self.output_root
        candidate = root / Path(storage_key)
        if _has_symlink_component(candidate, root):
            raise FileNotFoundError("Export is not available")
        path = candidate.resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise FileNotFoundError("Export is outside the output root") from None
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError("Export is not available")
        return path

    def csv_bytes(self, run_id: str, table: str) -> bytes:
        normalized = self.normalize_table(table)
        legacy, _ = self._resolve_completed_run(run_id)
        envelope = {
            "summary": self.adapter.summary(legacy.id),
            "candidates": self.adapter.candidates(legacy.id),
            "iterations": self.adapter.iterations(legacy.id),
            "supply": self.adapter.supply(legacy.id),
            "costs": self.adapter.costs(legacy.id),
            "decentral": self.adapter.decentral(legacy.id),
        }[normalized]
        if not envelope.available or envelope.data is None:
            raise ExportInputError(
                f"The {normalized} table is not available for this run."
            )
        rows = _rows_for_table(normalized, envelope.data)
        return _to_csv(rows)

    @staticmethod
    def normalize_table(table: str | None) -> str:
        normalized = (table or "").strip().lower().removesuffix(".csv")
        normalized = _TABLE_ALIASES.get(normalized, normalized)
        if normalized not in _ALLOWED_TABLES:
            allowed = ", ".join(sorted(_ALLOWED_TABLES))
            raise ExportInputError(f"Unknown export table. Choose one of: {allowed}.")
        return normalized

    def _resolve_completed_run(self, run_id: str) -> tuple[LegacyRun, dict[str, Any] | None]:
        managed: dict[str, Any] | None = None
        try:
            legacy = self.discovery.get_legacy_run(run_id)
        except FileNotFoundError:
            try:
                managed = RunRepository(self.engine).get(run_id)
            except MetadataNotFound:
                raise ExportInputError(f"Run {run_id} was not found.") from None
            if managed.get("status") != "completed":
                raise ExportInputError(f"Run {run_id} is not completed.")
            output_key = managed.get("output_storage_key")
            if not isinstance(output_key, str) or not output_key:
                raise ExportInputError(f"Run {run_id} has no output artifacts.")
            try:
                legacy = self.discovery.get_legacy_run(output_key)
            except FileNotFoundError:
                raise ExportInputError(f"Run {run_id} has no output artifacts.") from None
        if legacy.status != "completed":
            raise ExportInputError(f"Run {run_id} is incomplete.")
        return legacy, managed

    def _report_html(
        self,
        run: LegacyRun,
        managed: Mapping[str, Any] | None,
    ) -> str:
        summary = self.adapter.summary(run.id)
        costs = self.adapter.costs(run.id)
        supply = self.adapter.supply(run.id)
        candidates = self.adapter.candidates(run.id)
        summary_data = summary.data if summary.available and isinstance(summary.data, Mapping) else {}
        cost_data = costs.data if costs.available and isinstance(costs.data, Mapping) else {}
        supply_data = supply.data if supply.available and isinstance(supply.data, Mapping) else {}
        candidate_rows = candidates.data if candidates.available and isinstance(candidates.data, list) else []
        portfolio_values: dict[str, Any] = {}
        raw_portfolio = supply_data.get("supply") if isinstance(supply_data, Mapping) else None
        if isinstance(raw_portfolio, Mapping):
            for name, technology in raw_portfolio.items():
                portfolio_values[str(name)] = _technology_report_value(technology)
        if isinstance(supply_data, Mapping) and "total_heat_production_mwh" in supply_data:
            portfolio_values["total_heat_production_mwh"] = supply_data["total_heat_production_mwh"]
        title = (managed or {}).get("name") or run.to_schema().display_name
        generated = datetime.now(timezone.utc).isoformat()

        def metric_table(values: Mapping[str, Any]) -> str:
            rows = []
            for key, value in values.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    rows.append(
                        f"<tr><th scope=\"row\">{html.escape(str(key))}</th>"
                        f"<td>{html.escape(_display(value))}</td></tr>"
                    )
            return "<table><tbody>" + "".join(rows) + "</tbody></table>"

        candidate_html = "".join(
            "<tr>"
            + "".join(
                f"<td>{html.escape(_display(item.get(key)))}</td>"
                for key in ("id", "decision", "annual_heat_demand_mwh", "central_cost", "decentral_cost")
            )
            + "</tr>"
            for item in candidate_rows
            if isinstance(item, Mapping)
        )
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{html.escape(str(title))} — printable report</title>
<style>
@page {{ margin: 18mm; }}
body {{ color: #17212b; font: 14px/1.45 system-ui, sans-serif; margin: 0 auto; max-width: 1100px; }}
h1, h2 {{ color: #123b52; }}
.meta {{ color: #52636f; }}
.grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }}
section {{ break-inside: avoid; margin: 1.5rem 0; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #d7e0e5; padding: .4rem .5rem; text-align: left; }}
th {{ font-weight: 650; }}
@media print {{ .no-print {{ display: none; }} body {{ max-width: none; }} }}
</style></head><body>
<header><h1>{html.escape(str(title))}</h1>
<p class="meta">Scenario: {html.escape(run.scenario)} · generated {html.escape(generated)}</p>
<p class="no-print">Use the browser print dialog to save this report as PDF.</p></header>
<div class="grid"><section><h2>Summary</h2>{metric_table(summary_data)}</section>
<section><h2>Costs</h2>{metric_table(cost_data)}</section></div>
<section><h2>Supply portfolio</h2>{metric_table(portfolio_values)}</section>
<section><h2>Candidate decisions</h2>
<table><thead><tr><th>ID</th><th>Decision</th><th>Demand (MWh/a)</th><th>Central cost (€ / a)</th><th>Decentralized cost (€ / a)</th></tr></thead>
<tbody>{candidate_html or '<tr><td colspan="5">Candidate data unavailable.</td></tr>'}</tbody></table></section>
<footer class="meta"><p>DH-COMPASS {html.escape(__version__)} · This report is derived from immutable run artifacts.</p></footer>
</body></html>"""

    def _bundle_bytes(
        self,
        run: LegacyRun,
        managed: Mapping[str, Any] | None,
    ) -> bytes:
        entries: dict[str, bytes] = {}
        # A bundle is an export of documented run artifacts, not a general
        # archive endpoint.  In particular, never sweep arbitrary files (for
        # example credentials accidentally copied next to an output) into a
        # browser-downloadable ZIP.
        for artifact_id in _BUNDLE_ARTIFACT_IDS:
            artifact = run.artifact(artifact_id)
            if artifact is None or artifact.status != "available" or artifact.path is None:
                continue
            try:
                path = self.discovery.resolve_artifact(run.id, artifact_id)
                entries[artifact_id] = path.read_bytes()
            except (OSError, FileNotFoundError):
                continue

        manifest = self.discovery.load_json(run.id, "run_manifest.json")
        if "run_manifest.json" not in entries:
            manifest_data = (
                dict(manifest.value)
                if manifest.available and isinstance(manifest.value, Mapping)
                else {
                    "run_id": (managed or {}).get("id", run.id),
                    "application": {"version": __version__},
                    "status": "completed",
                }
            )
            entries["run_manifest.json"] = json.dumps(
                manifest_data, indent=2, ensure_ascii=False, default=str
            ).encode("utf-8")

        configuration: Mapping[str, Any] | None = None
        if managed and isinstance(managed.get("configuration_snapshot"), Mapping):
            configuration = managed["configuration_snapshot"]
        if not configuration and manifest.available and isinstance(manifest.value, Mapping):
            raw = manifest.value.get("configuration")
            if isinstance(raw, Mapping):
                configuration = raw
        entries["configuration.toml"] = self._configuration_toml(configuration).encode("utf-8")

        from dh_compass.reporting.attribution import OSM_PROVENANCE

        entries["data_provenance.json"] = json.dumps(OSM_PROVENANCE, ensure_ascii=False, indent=2).encode("utf-8")
        checksums = "\n".join(
            f"{_sha256_bytes(content)}  {name}" for name, content in sorted(entries.items())
        ) + "\n"
        entries["checksums.sha256"] = checksums.encode("utf-8")

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(entries.items()):
                archive.writestr(name, content)
        return output.getvalue()

    def _configuration_toml(self, configuration: Mapping[str, Any] | None) -> str:
        if configuration:
            try:
                return ConfigurationAdapter(self.project_root).export_toml(configuration)
            except Exception:
                pass
        return "# Configuration snapshot was not available in this legacy run.\n"


class RetentionService:
    """Remove only unreferenced generated exports, never completed run folders."""

    def __init__(self, output_root: str | Path, engine: Engine):
        self.output_root = Path(output_root).expanduser().resolve()
        self.engine = engine

    def cleanup(
        self,
        *,
        older_than_days: int,
        now: datetime | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if older_than_days < 0:
            raise ValueError("older_than_days must be nonnegative")
        reference = now or datetime.now(timezone.utc)
        cutoff = reference.timestamp() - older_than_days * 86_400
        jobs = ExportJobRepository(self.engine)
        candidates: list[dict[str, Any]] = []
        export_root = self.output_root / ".web_exports"
        if export_root.is_dir() and not export_root.is_symlink():
            for directory in export_root.iterdir():
                if not directory.is_dir() or directory.is_symlink():
                    continue
                try:
                    modified = directory.stat().st_mtime
                except OSError:
                    continue
                if modified >= cutoff:
                    continue
                # Only delete directories associated with an export job. A
                # referenced run output is never below this managed namespace.
                try:
                    job = jobs.get(directory.name)
                except MetadataNotFound:
                    continue
                candidates.append(job)

        removed = 0
        if not dry_run:
            for job in candidates:
                path = self._safe_path(job.get("storage_key"))
                if path is not None:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        continue
                directory = export_root / str(job["id"])
                try:
                    directory.rmdir()
                except OSError:
                    pass
                jobs.update(
                    str(job["id"]),
                    "failed",
                    error="Export removed by the retention policy.",
                )
                removed += 1
        return {
            "older_than_days": older_than_days,
            "dry_run": dry_run,
            "candidates": len(candidates),
            "removed": removed,
            "run_artifacts_preserved": True,
        }

    def _safe_path(self, storage_key: Any) -> Path | None:
        if not isinstance(storage_key, str):
            return None
        candidate = self.output_root / Path(storage_key)
        if _has_symlink_component(candidate, self.output_root):
            return None
        path = candidate.resolve()
        try:
            path.relative_to((self.output_root / ".web_exports").resolve())
        except ValueError:
            return None
        return path if not path.is_symlink() else None


def _has_symlink_component(path: Path, parent: Path) -> bool:
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


def _rows_for_table(table: str, data: Any) -> list[dict[str, Any]]:
    if table == "summary":
        return [dict(data)] if isinstance(data, Mapping) else []
    if table in {"candidates", "iterations", "decentral"}:
        return [dict(item) for item in data if isinstance(item, Mapping)] if isinstance(data, list) else []
    if table == "supply":
        portfolio = data.get("supply", {}) if isinstance(data, Mapping) else {}
        rows = []
        if isinstance(portfolio, Mapping):
            for name, value in portfolio.items():
                row = {"technology": name}
                if isinstance(value, Mapping):
                    row.update(value)
                rows.append(row)
        return rows
    if table == "costs":
        if not isinstance(data, Mapping):
            return []
        return [
            {"metric": key, "value": value}
            for key, value in data.items()
            if _csv_scalar(value)
        ]
    return []


def _to_csv(rows: list[dict[str, Any]]) -> bytes:
    fields = sorted({str(key) for row in rows for key in row})
    if not fields:
        fields = ["value"]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _csv_value(row.get(key)) for key in fields})
    return output.getvalue().encode("utf-8-sig")


def _csv_value(value: Any) -> str:
    if isinstance(value, (Mapping, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    text = "" if value is None else str(value)
    # Preserve real numeric negatives. For text values, prevent spreadsheet
    # formula execution when a CSV is opened in a desktop application.
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        if text.startswith(("=", "+", "-", "@")):
            return "'" + text
    return text


def _csv_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _technology_report_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        for key in ("annual_heat_energy_mwh", "annual_energy_mwh", "capacity_kw"):
            if key in value:
                return value[key]
    return value


def _display(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def _safe_component(value: str) -> str:
    cleaned = _SAFE_NAME.sub("_", str(value)).strip("._")
    return (cleaned or "export")[:100]


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


__all__ = ["ExportInputError", "ExportService", "RetentionService"]
