"""Comparison of completed legacy and managed DH-COMPASS runs.

The service intentionally consumes the same result adapter as the result API.
It does not recalculate optimization values and never compares arbitrary files
from a client supplied path.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine

from ..persistence.repositories import (
    MetadataNotFound,
    RunRepository,
    StudyAreaRepository,
)
from ..schemas.comparison import CompatibilityCheck
from .output_discovery import LegacyRun, OutputDiscoveryService
from .result_adapter import LegacyResultAdapter


class ComparisonInputError(ValueError):
    """Raised when one or more requested runs cannot be compared."""

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.details = dict(details or {})


@dataclass(slots=True)
class _RunSnapshot:
    requested_id: str
    result_id: str
    label: str
    status: str
    summary: dict[str, Any] = field(default_factory=dict)
    costs: dict[str, Any] = field(default_factory=dict)
    supply: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    network: dict[str, Any] = field(default_factory=dict)
    configuration: dict[str, Any] = field(default_factory=dict)
    study_area: Any = None
    data_revision: Any = None
    model_version: Any = None
    result_schema: Any = None
    scenario_revision_id: str | None = None
    preview_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ComparisonService:
    """Build deterministic, JSON-safe comparisons for two to four runs."""

    def __init__(
        self,
        discovery: OutputDiscoveryService,
        *,
        engine: Engine | None = None,
    ):
        self.discovery = discovery
        self.engine = engine
        self.adapter = LegacyResultAdapter(discovery)

    def compare(
        self,
        run_ids: list[str],
        *,
        include_unchanged_configuration: bool = False,
    ) -> dict[str, Any]:
        normalized = [str(item).strip() for item in run_ids]
        if not 2 <= len(normalized) <= 4:
            raise ComparisonInputError(
                "A comparison requires between two and four completed runs.",
                details={"run_ids": normalized},
            )
        if len(set(normalized)) != len(normalized):
            raise ComparisonInputError(
                "A comparison cannot contain the same run more than once.",
                details={"run_ids": normalized},
            )

        snapshots: list[_RunSnapshot] = []
        invalid: dict[str, str] = {}
        for run_id in normalized:
            try:
                snapshots.append(self._snapshot(run_id))
            except ComparisonInputError as exc:
                invalid[run_id] = str(exc)
        if invalid:
            raise ComparisonInputError(
                "Only completed runs with readable result artifacts can be compared.",
                details={"runs": invalid},
            )

        checks = self._compatibility(snapshots)
        warnings = [check.message for check in checks if check.status != "compatible"]
        baseline = snapshots[0].requested_id
        kpi_differences = self._metric_rows(snapshots, self._kpis)
        configuration_changes = self._configuration_changes(
            snapshots,
            include_unchanged=include_unchanged_configuration,
        )
        supply = self._supply_rows(snapshots)
        costs = self._cost_rows(snapshots)
        network = self._network_comparison(snapshots)

        return {
            "run_ids": normalized,
            "compatible": not any(check.status == "different" for check in checks),
            "compatibility": [check.model_dump(mode="json") for check in checks],
            "warnings": warnings,
            "runs": [
                {
                    "id": item.requested_id,
                    "label": item.label,
                    "status": item.status,
                    "scenario_revision_id": item.scenario_revision_id,
                    "preview_id": item.preview_id,
                    "model_version": item.model_version,
                    "result_schema": item.result_schema,
                }
                for item in snapshots
            ],
            "kpi_differences": kpi_differences,
            "kpis": kpi_differences,
            "configuration_changes": configuration_changes,
            "configuration": configuration_changes,
            "network": network,
            "supply": supply,
            "portfolio": supply,
            "costs": costs,
            "cost_differences": costs,
            "baseline_run_id": baseline,
        }

    def _snapshot(self, requested_id: str) -> _RunSnapshot:
        # A managed UUID is resolved through metadata only after the legacy
        # output lookup fails.  This keeps old output IDs with slashes intact.
        managed: dict[str, Any] | None = None
        try:
            legacy = self.discovery.get_legacy_run(requested_id)
        except FileNotFoundError:
            if self.engine is None:
                raise ComparisonInputError(f"Run {requested_id} was not found.") from None
            try:
                managed = RunRepository(self.engine).get(requested_id)
            except MetadataNotFound:
                raise ComparisonInputError(f"Run {requested_id} was not found.") from None
            if managed.get("status") != "completed":
                raise ComparisonInputError(
                    f"Run {requested_id} is not completed.",
                    details={"status": managed.get("status")},
                )
            output_id = managed.get("output_storage_key")
            if not isinstance(output_id, str) or not output_id:
                raise ComparisonInputError(f"Run {requested_id} has no result output.")
            try:
                legacy = self.discovery.get_legacy_run(output_id)
            except FileNotFoundError:
                raise ComparisonInputError(
                    f"Run {requested_id} has no readable result output."
                ) from None
        if legacy.status != "completed":
            raise ComparisonInputError(
                f"Run {requested_id} is incomplete.",
                details={"status": legacy.status},
            )

        manifest = self._manifest(legacy)
        summary = self._data(self.adapter.summary(legacy.id))
        costs = self._data(self.adapter.costs(legacy.id))
        supply = self._data(self.adapter.supply(legacy.id))
        candidates_value = self._data(self.adapter.candidates(legacy.id))
        candidates = candidates_value if isinstance(candidates_value, list) else []
        network = self._data(
            self.adapter.network(legacy.id, layers={"final_network"})
        )
        if not isinstance(summary, dict):
            summary = {}
        if not isinstance(costs, dict):
            costs = {}
        if not isinstance(supply, dict):
            supply = {}
        if not isinstance(network, dict):
            network = {}

        configuration: dict[str, Any] = {}
        if managed and isinstance(managed.get("configuration_snapshot"), Mapping):
            configuration = deepcopy(dict(managed["configuration_snapshot"]))
        if isinstance(manifest.get("configuration"), Mapping):
            configuration = deepcopy(dict(manifest["configuration"]))

        application = manifest.get("application")
        if not isinstance(application, Mapping):
            application = {}
        model_version = (
            manifest.get("model_version")
            or manifest.get("application_version")
            or application.get("version")
            or (managed or {}).get("application_version")
        )
        result_schema = (
            manifest.get("result_schema_version")
            or manifest.get("result_schema")
            or application.get("result_schema_version")
            or "legacy-v1"
        )
        study_area = (
            manifest.get("study_area")
            or manifest.get("area")
            or manifest.get("execution_bbox")
        )
        scenario_revision_id = None
        preview_id = None
        data_revision: Any = None
        if managed:
            scenario_revision_id = _optional_str(managed.get("scenario_revision_id"))
            preview_id = _optional_str(managed.get("preview_id"))
            if self.engine is not None:
                area = StudyAreaRepository(self.engine).get(str(managed["scenario_id"]))
                if area is not None:
                    study_area = area.get("execution_bbox") or area.get("display_geometry")
            data_revision = (
                manifest.get("input_revision")
                or manifest.get("data_revision")
                or preview_id
            )
        else:
            scenario_revision_id = _optional_str(manifest.get("scenario_revision_id"))
            preview_id = _optional_str(manifest.get("preview_id"))
            data_revision = manifest.get("input_revision") or manifest.get("data_revision")
            if data_revision is None:
                data_revision = preview_id

        return _RunSnapshot(
            requested_id=requested_id,
            result_id=legacy.id,
            label=(managed or {}).get("name") or legacy.to_schema().display_name,
            status="completed",
            summary=summary,
            costs=costs,
            supply=supply,
            candidates=[dict(item) for item in candidates if isinstance(item, Mapping)],
            network=network,
            configuration=configuration,
            study_area=deepcopy(study_area),
            data_revision=data_revision,
            model_version=model_version,
            result_schema=result_schema,
            scenario_revision_id=scenario_revision_id,
            preview_id=preview_id,
            metadata=manifest,
        )

    def _manifest(self, run: LegacyRun) -> dict[str, Any]:
        document = self.discovery.load_json(run.id, "run_manifest.json")
        return dict(document.value) if document.available and isinstance(document.value, Mapping) else {}

    @staticmethod
    def _data(envelope: Any) -> Any:
        return deepcopy(envelope.data) if getattr(envelope, "available", False) else None

    @staticmethod
    def _compatibility(snapshots: list[_RunSnapshot]) -> list[CompatibilityCheck]:
        definitions = (
            ("study_area", "study areas"),
            ("data_revision", "input data revisions"),
            ("model_version", "application/model versions"),
            ("result_schema", "result schemas"),
        )
        checks: list[CompatibilityCheck] = []
        for key, label in definitions:
            values = {item.requested_id: getattr(item, key) for item in snapshots}
            known = [value for value in values.values() if value is not None]
            if len(known) < len(values) or not known:
                checks.append(
                    CompatibilityCheck(
                        key=key,  # type: ignore[arg-type]
                        status="unknown",
                        values=values,
                        message=f"The {label} could not be verified for every run.",
                    )
                )
                continue
            normalized = {_canonical(value) for value in known}
            if len(normalized) == 1:
                checks.append(
                    CompatibilityCheck(
                        key=key,  # type: ignore[arg-type]
                        status="compatible",
                        values=values,
                        message=f"The {label} match.",
                    )
                )
            else:
                checks.append(
                    CompatibilityCheck(
                        key=key,  # type: ignore[arg-type]
                        status="different",
                        values=values,
                        message=f"The {label} differ; interpret deltas with care.",
                    )
                )
        return checks

    _kpis = (
        "total_heat_demand_mwh",
        "connected_heat_demand_mwh",
        "disconnected_heat_demand_mwh",
        "connected_share_pct",
        "total_subgraphs",
        "connected_subgraphs",
        "disconnected_subgraphs",
        "connected_buildings",
        "total_buildings",
        "total_network_length_m",
        "peak_load_kw",
        "total_annualized_eur",
    )

    def _metric_rows(
        self,
        snapshots: list[_RunSnapshot],
        names: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        baseline_id = snapshots[0].requested_id
        for name in names:
            values = {
                item.requested_id: _lookup_metric(item, name) for item in snapshots
            }
            if not any(value is not None for value in values.values()):
                continue
            baseline = values.get(baseline_id)
            deltas = {
                key: _delta(value, baseline) for key, value in values.items()
            }
            rows.append(
                {
                    "key": name,
                    "values": values,
                    "baseline_value": baseline,
                    "deltas": deltas,
                    "delta": deltas.get(snapshots[1].requested_id),
                }
            )
        return rows

    def _configuration_changes(
        self,
        snapshots: list[_RunSnapshot],
        *,
        include_unchanged: bool,
    ) -> list[dict[str, Any]]:
        flattened = [_flatten(item.configuration) for item in snapshots]
        paths = sorted({path for values in flattened for path in values})
        result: list[dict[str, Any]] = []
        for path in paths:
            values = {
                item.requested_id: flattened[index].get(path)
                for index, item in enumerate(snapshots)
            }
            changed = len({_canonical(value) for value in values.values()}) > 1
            if not include_unchanged and not changed:
                continue
            result.append(
                {
                    "path": path,
                    "values": values,
                    "changed": changed,
                    "setting_type": (
                        "standard"
                        if path == "network.linear_heat_density_threshold"
                        else "expert"
                    ),
                }
            )
        return result

    def _supply_rows(self, snapshots: list[_RunSnapshot]) -> list[dict[str, Any]]:
        names = sorted(
            {
                str(name)
                for item in snapshots
                for name in (
                    item.supply.get("supply", {})
                    if isinstance(item.supply.get("supply"), Mapping)
                    else {}
                )
            }
        )
        rows: list[dict[str, Any]] = []
        baseline_id = snapshots[0].requested_id
        for name in names:
            values: dict[str, Any] = {}
            for item in snapshots:
                supply = item.supply.get("supply", {})
                technology = supply.get(name) if isinstance(supply, Mapping) else None
                values[item.requested_id] = _technology_value(technology)
            baseline = values.get(baseline_id)
            rows.append(
                {
                    "technology": name,
                    "values": values,
                    "baseline_value": baseline,
                    "deltas": {key: _delta(value, baseline) for key, value in values.items()},
                    "delta": _delta(values.get(snapshots[1].requested_id), baseline),
                }
            )
        return rows

    def _cost_rows(self, snapshots: list[_RunSnapshot]) -> list[dict[str, Any]]:
        names = sorted(
            {
                str(key)
                for item in snapshots
                for key, value in item.costs.items()
                if _is_scalar_number(value)
            }
        )
        rows: list[dict[str, Any]] = []
        baseline_id = snapshots[0].requested_id
        for name in names:
            values = {
                item.requested_id: item.costs.get(name) for item in snapshots
            }
            baseline = values.get(baseline_id)
            rows.append(
                {
                    "key": name,
                    "values": values,
                    "baseline_value": baseline,
                    "deltas": {key: _delta(value, baseline) for key, value in values.items()},
                    "delta": _delta(values.get(snapshots[1].requested_id), baseline),
                }
            )
        return rows

    @staticmethod
    def _network_comparison(snapshots: list[_RunSnapshot]) -> dict[str, Any]:
        records = []
        for item in snapshots:
            final = item.network.get("final_network")
            features = final.get("features", []) if isinstance(final, Mapping) else []
            records.append(
                {
                    "run_id": item.requested_id,
                    "available": bool(item.network.get("availability", {}).get("final_network")),
                    "feature_count": len(features) if isinstance(features, list) else 0,
                    "final_network": final,
                }
            )
        return {"runs": records}


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {prefix: value} if prefix else {}
    result: dict[str, Any] = {}
    for key in sorted(value, key=str):
        path = f"{prefix}.{key}" if prefix else str(key)
        nested = value[key]
        if isinstance(nested, Mapping):
            result.update(_flatten(nested, path))
        else:
            result[path] = deepcopy(nested)
    return result


def _lookup_metric(snapshot: _RunSnapshot, key: str) -> Any:
    if key in snapshot.summary:
        return snapshot.summary[key]
    if key == "total_annualized_eur":
        return snapshot.costs.get(key)
    if key == "total_buildings":
        return snapshot.summary.get("connected_buildings")
    return None


def _technology_value(value: Any) -> Any:
    if _is_scalar_number(value):
        return value
    if not isinstance(value, Mapping):
        return None
    for key in ("annual_heat_energy_mwh", "annual_energy_mwh", "capacity_kw"):
        if _is_scalar_number(value.get(key)):
            return value[key]
    return None


def _delta(value: Any, baseline: Any) -> float | None:
    if not _is_scalar_number(value) or not _is_scalar_number(baseline):
        return None
    return float(value) - float(baseline)


def _is_scalar_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(value)


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


__all__ = ["ComparisonInputError", "ComparisonService"]
