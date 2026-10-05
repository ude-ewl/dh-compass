"""Adapters from legacy JSON/GeoJSON artifacts to browser result sections."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..schemas.results import ResultEnvelope
from .output_discovery import (
    DocumentLoad,
    LegacyRun,
    OutputDiscoveryService,
    _enrich_summary,
)

_TIMESERIES_JSON_ARTIFACTS = (
    "timeseries.json",
    "time_series.json",
    "results_timeseries.json",
)
_TIMESERIES_CSV_ARTIFACTS = ("timeseries.csv", "time_series.csv")
_DEFAULT_MAX_POINTS = 5_000


class LegacyResultAdapter:
    """Build stable result sections without exposing artifact implementation details."""

    def __init__(self, discovery: OutputDiscoveryService):
        self.discovery = discovery

    def summary(self, run_id: str) -> ResultEnvelope:
        run = self.discovery.get_legacy_run(run_id)
        document = self._preferred_document(run, ("full_results.json", "viewer_data.json"))
        if not document.available or not isinstance(document.value, Mapping):
            return self._unavailable(
                document,
                warning="A valid full-results or viewer-data document is not available.",
            )
        summary = _enrich_summary(document.value)
        if summary is None:
            return ResultEnvelope(
                available=False,
                source_artifacts=[document.artifact.id] if document.artifact else [],
                warnings=["The result document does not contain a summary section."],
            )
        # Older full-results exports omit connecting-pipeline length. The viewer
        # records it for every accepted subgraph; do not sum rejected trial paths.
        sources = [document.artifact.id] if document.artifact else []
        if "final_connection_length_m" not in summary:
            combined = document.value.get("combined_graph")
            viewer = self.discovery.load_json(run.id, "viewer_data.json")
            if isinstance(combined, Mapping) and viewer.available and isinstance(viewer.value, Mapping):
                candidates = viewer.value.get("subgraphs")
                if isinstance(candidates, Mapping):
                    accepted = [item for item in candidates.values() if isinstance(item, Mapping) and item.get("is_connected")]
                    lengths = [_number_or_none(item.get("connection_length_m")) for item in accepted]
                    network_length = _number_or_none(combined.get("total_network_length_m"))
                    if accepted and all(length is not None for length in lengths) and network_length is not None:
                        length = network_length + sum(lengths)
                        summary["final_connection_length_m"] = length
                        demand = _number_or_none(summary.get("connected_heat_demand_mwh"))
                        if demand is not None and length > 0:
                            summary["average_linear_heat_density_mwh_per_m_a"] = demand / length
                        sources.append("viewer_data.json")
        return ResultEnvelope(
            available=True,
            data=deepcopy(summary),
            source_artifacts=sources,
        )

    def network(
        self, run_id: str, *, layers: set[str] | None = None
    ) -> ResultEnvelope:
        """Return only requested map layers when a client provides a layer set.

        The legacy endpoint remains backwards compatible when ``layers`` is
        omitted.  New clients request the base layers first and defer large
        optional layers such as LHD until the user enables them.
        """

        run = self.discovery.get_legacy_run(run_id)
        warnings: list[str] = []
        source_artifacts: list[str] = []
        wanted = (
            layers
            if layers is not None
            else {
                "final_network",
                "candidate_network",
                "lhd",
                "connection_paths",
            }
        )

        final_network = (
            self._load(run, "final_network.geojson", warnings, source_artifacts)
            if "final_network" in wanted
            else None
        )
        lhd = (
            self._load(run, "lhd_graph.geojson", warnings, source_artifacts)
            if "lhd" in wanted
            else None
        )
        candidate_network = _empty_feature_collection()
        paths = _empty_feature_collection()
        needs_viewer = bool({"candidate_network", "connection_paths", "lhd"} & wanted)
        viewer_document = self.discovery.load_json(run.id, "viewer_data.json")
        if needs_viewer and viewer_document.artifact is not None:
            source_artifacts.append("viewer_data.json")
        if needs_viewer and viewer_document.status == "invalid":
            warnings.append(viewer_document.error or "viewer_data.json is malformed.")
        if needs_viewer and viewer_document.available and isinstance(viewer_document.value, Mapping):
            if "lhd" in wanted and lhd is None:
                candidate_lhd = viewer_document.value.get("lhd_edges_geojson")
                if isinstance(candidate_lhd, Mapping):
                    lhd = deepcopy(dict(candidate_lhd))
            if "candidate_network" in wanted:
                candidate_network = _candidate_network(viewer_document.value.get("subgraphs"))
            if "connection_paths" in wanted:
                paths = _connection_paths(viewer_document.value.get("iterations"))

        data = {
            "final_network": final_network,
            "candidate_network": candidate_network,
            "lhd": lhd,
            "connection_paths": paths,
            "availability": {
                "final_network": final_network is not None,
                "candidate_network": bool(candidate_network["features"]),
                "lhd": lhd is not None,
                "connection_paths": bool(paths["features"]),
            },
        }
        available = any(
            data["availability"][key]
            for key in ("final_network", "candidate_network", "lhd", "connection_paths")
        )
        return ResultEnvelope(
            available=available,
            data=data if available else None,
            source_artifacts=_unique(source_artifacts),
            warnings=warnings,
        )

    def iterations(self, run_id: str) -> ResultEnvelope:
        run = self.discovery.get_legacy_run(run_id)
        document = self.discovery.load_json(run.id, "viewer_data.json")
        if not document.available or not isinstance(document.value, Mapping):
            return self._unavailable(document, warning="Decision playback data is not available.")
        iterations = document.value.get("iterations")
        if not isinstance(iterations, list):
            return ResultEnvelope(
                available=False,
                source_artifacts=["viewer_data.json"],
                warnings=["The viewer document does not contain iteration data."],
            )
        return ResultEnvelope(
            available=True,
            data=deepcopy(iterations),
            source_artifacts=["viewer_data.json"],
        )

    def candidates(self, run_id: str) -> ResultEnvelope:
        run = self.discovery.get_legacy_run(run_id)
        viewer = self.discovery.load_json(run.id, "viewer_data.json")
        if viewer.available and isinstance(viewer.value, Mapping):
            raw = viewer.value.get("subgraphs")
            candidates = _normalize_viewer_candidates(raw)
            if candidates:
                return ResultEnvelope(
                    available=True,
                    data=candidates,
                    source_artifacts=["viewer_data.json"],
                )

        full = self.discovery.load_json(run.id, "full_results.json")
        if full.available and isinstance(full.value, Mapping):
            raw = full.value.get("subgraphs")
            candidates = _normalize_full_candidates(raw)
            if candidates:
                return ResultEnvelope(
                    available=True,
                    data=candidates,
                    source_artifacts=["full_results.json"],
                    warnings=(
                        ["Candidate geometry and decision playback are unavailable."]
                        if not viewer.available
                        else []
                    ),
                )
        warnings = ["Candidate records are not available."]
        if viewer.status == "invalid":
            warnings.append(viewer.error or "The viewer document is malformed.")
        return ResultEnvelope(
            available=False,
            source_artifacts=[
                artifact_id
                for artifact_id, document in (
                    ("viewer_data.json", viewer),
                    ("full_results.json", full),
                )
                if document.artifact is not None
            ],
            warnings=warnings,
        )

    def candidate(self, run_id: str, candidate_id: int) -> ResultEnvelope:
        candidates = self.candidates(run_id)
        if not candidates.available or not isinstance(candidates.data, list):
            return candidates
        candidate = next(
            (
                item
                for item in candidates.data
                if isinstance(item, Mapping) and _candidate_id(item.get("id")) == candidate_id
            ),
            None,
        )
        if candidate is None:
            return ResultEnvelope(
                available=False,
                source_artifacts=candidates.source_artifacts,
                warnings=[f"Candidate {candidate_id} was not found."],
            )

        result = deepcopy(dict(candidate))
        iterations = self.iterations(run_id)
        if iterations.available and isinstance(iterations.data, list):
            for iteration in iterations.data:
                if isinstance(iteration, Mapping) and _candidate_id(iteration.get("subgraph_id")) == candidate_id:
                    result["iteration_step"] = iteration.get("step")
                    result["decision"] = iteration.get("decision", result.get("decision"))
                    result["decision_margin_eur"] = _number(
                        iteration.get("decentral_cost")
                    ) - _number(iteration.get("marginal_central_cost"))
                    break
        return ResultEnvelope(
            available=True,
            data=result,
            source_artifacts=candidates.source_artifacts,
            warnings=candidates.warnings,
        )

    def supply(self, run_id: str) -> ResultEnvelope:
        run = self.discovery.get_legacy_run(run_id)
        full = self.discovery.load_json(run.id, "full_results.json")
        viewer = self.discovery.load_json(run.id, "viewer_data.json")
        portfolio: Mapping[str, Any] | None = None
        source_artifacts: list[str] = []

        if full.available and isinstance(full.value, Mapping):
            combined = full.value.get("combined_graph")
            if isinstance(combined, Mapping) and (
                "supply" in combined or "storage" in combined
            ):
                portfolio = combined
                source_artifacts.append("full_results.json")

        if portfolio is None and viewer.available and isinstance(viewer.value, Mapping):
            iterations = viewer.value.get("iterations")
            supplies: list[Mapping[str, Any]] = []
            if isinstance(iterations, list):
                supplies.extend(
                    iteration.get("cumulative_supply")
                    for iteration in iterations
                    if isinstance(iteration, Mapping)
                    and iteration.get("decision") == "connected"
                    and isinstance(iteration.get("cumulative_supply"), Mapping)
                )
            if supplies:
                portfolio = supplies[-1]
                source_artifacts.append("viewer_data.json")

        if portfolio is None:
            return ResultEnvelope(
                available=False,
                source_artifacts=["full_results.json", "viewer_data.json"],
                warnings=["Supply portfolio data is not available."],
            )

        supply = portfolio.get("supply", {})
        supply_mapping = dict(supply) if isinstance(supply, Mapping) else {}
        data: dict[str, Any] = {
            "supply": deepcopy(supply_mapping),
            "storage": deepcopy(dict(portfolio.get("storage", {})))
            if isinstance(portfolio.get("storage", {}), Mapping)
            else {},
            "total_heat_production_mwh": portfolio.get("total_heat_production_mwh"),
        }
        # Potential limits are stored only in viewer_data.json.  Preserve this
        # legacy information even when the richer full-results portfolio wins.
        if viewer.available and isinstance(viewer.value, Mapping):
            limits = viewer.value.get("potential_limits")
            if isinstance(limits, Mapping):
                data["resources"] = _resource_utilization(limits, supply_mapping)
                source_artifacts.append("viewer_data.json")
        return ResultEnvelope(
            available=True,
            data=data,
            source_artifacts=_unique(source_artifacts),
        )

    def costs(self, run_id: str) -> ResultEnvelope:
        run = self.discovery.get_legacy_run(run_id)
        full = self.discovery.load_json(run.id, "full_results.json")
        if full.available and isinstance(full.value, Mapping):
            combined = full.value.get("combined_graph")
            if isinstance(combined, Mapping) and isinstance(combined.get("cost"), Mapping):
                return ResultEnvelope(
                    available=True,
                    data=deepcopy(dict(combined["cost"])),
                    source_artifacts=["full_results.json"],
                )

        viewer = self.discovery.load_json(run.id, "viewer_data.json")
        if viewer.available and isinstance(viewer.value, Mapping):
            iterations = viewer.value.get("iterations")
            if isinstance(iterations, list) and iterations:
                last = iterations[-1]
                if isinstance(last, Mapping):
                    fields = {
                        "total_annualized_eur": last.get("central_cost_total"),
                        "marginal_annualized_eur": last.get("marginal_central_cost"),
                        "decentral_annualized_eur": last.get("decentral_cost"),
                    }
                    if any(value is not None for value in fields.values()):
                        return ResultEnvelope(
                            available=True,
                            data=fields,
                            source_artifacts=["viewer_data.json"],
                            warnings=["Only iteration-level cost values are available."],
                        )
        return ResultEnvelope(
            available=False,
            source_artifacts=["full_results.json", "viewer_data.json"],
            warnings=["Cost breakdown data is not available."],
        )

    def decentral(self, run_id: str) -> ResultEnvelope:
        """Return a stable central/decentralized comparison resource.

        ``full_results.json`` contains the richer cluster shape, while older
        viewer exports keep the comparison values directly on each candidate.
        Both are normalized into one list without treating missing cluster
        details as an empty optimization result.
        """

        run = self.discovery.get_legacy_run(run_id)
        full = self.discovery.load_json(run.id, "full_results.json")
        viewer = self.discovery.load_json(run.id, "viewer_data.json")
        records: list[dict[str, Any]] = []
        source_artifacts: list[str] = []

        if full.available and isinstance(full.value, Mapping):
            raw = full.value.get("subgraphs")
            if isinstance(raw, list):
                source_artifacts.append("full_results.json")
                records = [_decentral_record(item) for item in raw if isinstance(item, Mapping)]

        viewer_records: list[dict[str, Any]] = []
        if viewer.available and isinstance(viewer.value, Mapping):
            raw = viewer.value.get("subgraphs")
            if isinstance(raw, Mapping):
                viewer_records = [
                    _decentral_record(dict(value, subgraph_id=key))
                    for key, value in raw.items()
                    if isinstance(value, Mapping)
                ]

        if records and viewer_records:
            # The full-results adapter has authoritative central metrics, but
            # the viewer often contains the only decentralized cost values.
            # Enrich by ID rather than making the UI choose an artifact.
            viewer_by_id = {item["id"]: item for item in viewer_records}
            for record in records:
                supplement = viewer_by_id.get(record["id"])
                if not supplement:
                    continue
                for key in (
                    "decentral_cost",
                    "difference_eur",
                    "clusters",
                    "supply",
                    "storage",
                    "total_heat_production_mwh",
                ):
                    current = record.get(key)
                    if current is None or current == [] or current == {}:
                        record[key] = deepcopy(supplement.get(key))
                record["clusters_available"] = bool(record.get("clusters"))
            if any(
                record.get("decentral_cost") is not None
                or record.get("clusters_available")
                for record in records
            ):
                source_artifacts.append("viewer_data.json")
        elif viewer_records:
            source_artifacts.append("viewer_data.json")
            records = viewer_records

        records = sorted(records, key=lambda item: (_candidate_id(item.get("id")), str(item.get("id"))))
        if records:
            return ResultEnvelope(
                available=True,
                data=records,
                source_artifacts=_unique(source_artifacts),
                warnings=(
                    ["Cluster details are not available for one or more candidates."]
                    if any(not item.get("clusters_available", False) for item in records)
                    else []
                ),
            )

        return ResultEnvelope(
            available=False,
            source_artifacts=[
                artifact_id
                for artifact_id, document in (
                    ("full_results.json", full),
                    ("viewer_data.json", viewer),
                )
                if document.artifact is not None
            ],
            warnings=["Decentralized comparison data is not available."],
        )

    def timeseries(
        self,
        run_id: str,
        *,
        series: str | Sequence[str] | None = None,
        max_points: int | None = None,
        resolution: int | None = None,
    ) -> ResultEnvelope:
        """Read and bound an optional time-series export.

        Time series can be large enough to freeze a browser.  The adapter
        filters named series before applying deterministic evenly-spaced
        sampling, preserving the first and last observations.  The response
        records both original and returned point counts for honest UI labels.
        """

        run = self.discovery.get_legacy_run(run_id)
        document: DocumentLoad | None = None
        rows: list[dict[str, Any]] | None = None
        source_artifact: str | None = None

        for artifact_id in _TIMESERIES_JSON_ARTIFACTS:
            candidate = self.discovery.load_json(run.id, artifact_id)
            if candidate.available:
                document = candidate
                source_artifact = artifact_id
                rows = _timeseries_rows(candidate.value)
                break
            if candidate.artifact is not None and document is None:
                document = candidate

        if rows is None:
            for artifact_id in _TIMESERIES_CSV_ARTIFACTS:
                artifact = run.artifact(artifact_id)
                if artifact is None:
                    continue
                if artifact.status != "available" or artifact.path is None:
                    document = DocumentLoad(
                        status=artifact.status,
                        artifact=artifact,
                        error=artifact.error,
                    )
                    continue
                document = DocumentLoad(status="available", artifact=artifact)
                source_artifact = artifact_id
                rows = _read_timeseries_csv(artifact.path)
                break

        if rows is None:
            # Some integrations embed an optional series in the report JSON
            # instead of writing a separate export.  It is still normalized
            # and bounded before reaching the browser.
            full = self.discovery.load_json(run.id, "full_results.json")
            if full.available and isinstance(full.value, Mapping):
                embedded = next(
                    (
                        full.value.get(key)
                        for key in ("timeseries", "time_series", "time_series_data")
                        if full.value.get(key) is not None
                    ),
                    None,
                )
                if embedded is None and isinstance(full.value.get("combined_graph"), Mapping):
                    combined = full.value["combined_graph"]
                    embedded = next(
                        (
                            combined.get(key)
                            for key in ("timeseries", "time_series", "time_series_data")
                            if combined.get(key) is not None
                        ),
                        None,
                    )
                rows = _timeseries_rows(embedded)
                if rows is not None:
                    document = full
                    source_artifact = "full_results.json"

        if rows is None or document is None or not document.available:
            warning = "Optional time-series data is not available."
            if document is not None and document.error and document.status == "invalid":
                warning = f"Time-series data is invalid: {document.error}"
            return ResultEnvelope(
                available=False,
                source_artifacts=(
                    [source_artifact]
                    if source_artifact
                    else [document.artifact.id]
                    if document is not None and document.artifact is not None
                    else []
                ),
                warnings=[warning],
            )

        selected = _requested_series(series)
        if selected:
            rows = [
                {
                    key: value
                    for key, value in row.items()
                    if key in selected or key in {"timestamp", "time", "datetime", "date"}
                }
                for row in rows
            ]
        original_points = len(rows)
        limit = max(1, int(resolution or max_points or _DEFAULT_MAX_POINTS))
        sampled = _downsample_rows(rows, limit)
        return ResultEnvelope(
            available=True,
            data={
                "points": sampled,
                "series": _series_from_rows(sampled),
                "series_names": sorted(
                    {
                        key
                        for row in rows
                        for key, value in row.items()
                        if key not in {"timestamp", "time", "datetime", "date"}
                        and _is_number(value)
                    }
                ),
                "original_points": original_points,
                "returned_points": len(sampled),
                "downsampled": len(sampled) < original_points,
                "max_points": limit,
            },
            source_artifacts=[source_artifact] if source_artifact else [],
        )

    def performance(self, run_id: str) -> ResultEnvelope:
        run = self.discovery.get_legacy_run(run_id)
        document = self.discovery.load_json(run.id, "performance_metrics.json")
        if not document.available:
            return self._unavailable(document, warning="Performance metrics are not available.")
        return ResultEnvelope(
            available=True,
            data=deepcopy(document.value),
            source_artifacts=["performance_metrics.json"],
        )

    def _preferred_document(
        self, run: LegacyRun, artifact_ids: tuple[str, ...]
    ) -> DocumentLoad:
        for artifact_id in artifact_ids:
            document = self.discovery.load_json(run.id, artifact_id)
            if document.available and isinstance(document.value, Mapping):
                if _enrich_summary(document.value) is not None:
                    return document
        return self.discovery.load_json(run.id, artifact_ids[0])

    def _load(
        self,
        run: LegacyRun,
        artifact_id: str,
        warnings: list[str],
        source_artifacts: list[str],
    ) -> dict[str, Any] | None:
        document = self.discovery.load_json(run.id, artifact_id)
        if document.artifact is not None:
            source_artifacts.append(artifact_id)
        if document.status == "invalid":
            warnings.append(document.error or f"{artifact_id} is malformed.")
        if document.available and isinstance(document.value, Mapping):
            return deepcopy(dict(document.value))
        return None

    @staticmethod
    def _unavailable(document: DocumentLoad, *, warning: str) -> ResultEnvelope:
        warnings = [warning]
        if document.error and document.status == "invalid":
            warnings.append(document.error)
        return ResultEnvelope(
            available=False,
            source_artifacts=[document.artifact.id] if document.artifact else [],
            warnings=warnings,
        )


def _empty_feature_collection() -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": []}


def _candidate_network(raw: Any) -> dict[str, Any]:
    collection = _empty_feature_collection()
    if not isinstance(raw, Mapping):
        return collection
    for key, candidate in raw.items():
        if not isinstance(candidate, Mapping):
            continue
        candidate_id = _candidate_id(key)
        decision = "connected" if candidate.get("is_connected") else "rejected"
        edges = candidate.get("edges_geojson")
        if not isinstance(edges, Mapping) or not isinstance(edges.get("features"), list):
            continue
        for feature in edges["features"]:
            if not isinstance(feature, Mapping):
                continue
            enriched = deepcopy(dict(feature))
            properties = dict(enriched.get("properties") or {})
            properties.update({"candidate_id": candidate_id, "decision": decision})
            enriched["properties"] = properties
            collection["features"].append(enriched)
    return collection


def _connection_paths(raw: Any) -> dict[str, Any]:
    collection = _empty_feature_collection()
    if not isinstance(raw, list):
        return collection
    for iteration in raw:
        if not isinstance(iteration, Mapping) or iteration.get("decision") != "connected":
            continue
        geometry = iteration.get("connecting_path_geojson")
        if not isinstance(geometry, Mapping):
            continue
        for feature in geometry.get("features", []):
            if not isinstance(feature, Mapping):
                continue
            enriched = deepcopy(dict(feature))
            properties = dict(enriched.get("properties") or {})
            properties.update(
                {
                    "candidate_id": _candidate_id(iteration.get("subgraph_id")),
                    "step": iteration.get("step"),
                    "decision": iteration.get("decision"),
                }
            )
            enriched["properties"] = properties
            collection["features"].append(enriched)
    return collection


def _normalize_viewer_candidates(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, Mapping):
        return []
    result: list[dict[str, Any]] = []
    for key, value in raw.items():
        if not isinstance(value, Mapping):
            continue
        candidate = deepcopy(dict(value))
        candidate["id"] = _candidate_id(key)
        candidate["decision"] = "connected" if value.get("is_connected") else "rejected"
        if "avg_lhd" in value and "average_linear_heat_density_mwh_per_m_a" not in value:
            candidate["average_linear_heat_density_mwh_per_m_a"] = value["avg_lhd"]
        candidate.setdefault("central_cost", value.get("central_cost"))
        candidate.setdefault("decentral_cost", value.get("decentral_cost"))
        candidate["difference_eur"] = _difference(
            candidate.get("central_cost"), candidate.get("decentral_cost")
        )
        result.append(candidate)
    return sorted(result, key=lambda item: (_candidate_id(item.get("id")), str(item.get("id"))))


def _normalize_full_candidates(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for value in raw:
        if not isinstance(value, Mapping):
            continue
        candidate = deepcopy(dict(value))
        candidate["id"] = _candidate_id(value.get("subgraph_id"))
        candidate["decision"] = "connected" if value.get("is_connected") else "rejected"
        alternative = value.get("decentral_alternative")
        if not isinstance(alternative, Mapping):
            alternative = value.get("decentral_supply")
        if not isinstance(alternative, Mapping):
            alternative = {}
        if candidate.get("central_cost") is None:
            candidate["central_cost"] = _nested_number(
                value, "central_cumulative_supply", "cost_annualized_eur"
            )
        if candidate.get("decentral_cost") is None:
            candidate["decentral_cost"] = alternative.get("total_annualized_cost_eur")
        candidate["difference_eur"] = _difference(
            candidate.get("central_cost"), candidate.get("decentral_cost")
        )
        if not candidate.get("clusters"):
            candidate["clusters"] = alternative.get("clusters", [])
        result.append(candidate)
    return sorted(result, key=lambda item: (_candidate_id(item.get("id")), str(item.get("id"))))


def _decentral_record(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one full-results/viewer candidate for the decentral tab."""

    identifier = _candidate_id(value.get("id", value.get("subgraph_id")))
    decision = value.get("decision")
    if decision not in {"connected", "rejected"}:
        decision = "connected" if value.get("is_connected") else "rejected"

    alternative = value.get("decentral_alternative")
    if not isinstance(alternative, Mapping):
        alternative = value.get("decentral_supply")
    if not isinstance(alternative, Mapping):
        alternative = {}

    clusters = alternative.get("clusters")
    if not isinstance(clusters, list):
        clusters = value.get("clusters")
    if not isinstance(clusters, list):
        clusters = []

    central_cost = _first_number(
        value.get("central_cost"),
        value.get("central_cost_annualized_eur"),
        _nested_number(value, "central_cumulative_supply", "cost_annualized_eur"),
    )
    decentral_cost = _first_number(
        value.get("decentral_cost"),
        value.get("decentral_cost_annualized_eur"),
        alternative.get("total_annualized_cost_eur"),
    )
    supply = alternative.get("aggregated_supply")
    if not isinstance(supply, Mapping):
        supply = value.get("supply") if isinstance(value.get("supply"), Mapping) else {}
    storage = alternative.get("storage")
    if not isinstance(storage, Mapping):
        storage = value.get("storage") if isinstance(value.get("storage"), Mapping) else {}

    result: dict[str, Any] = {
        "id": identifier,
        "decision": decision,
        "annual_heat_demand_mwh": value.get("annual_heat_demand_mwh"),
        "buildings": value.get("buildings"),
        "central_cost": central_cost,
        "decentral_cost": decentral_cost,
        "difference_eur": (
            decentral_cost - central_cost
            if central_cost is not None and decentral_cost is not None
            else None
        ),
        "clusters": deepcopy(clusters),
        "clusters_available": bool(clusters),
        "supply": deepcopy(dict(supply)),
        "storage": deepcopy(dict(storage)),
        "total_heat_production_mwh": alternative.get(
            "aggregated_total_energy_mwh", value.get("total_heat_production_mwh")
        ),
    }
    # Preserve useful raw values without exposing an internal artifact shape as
    # the primary contract.  The UI can display these optional metrics when
    # present and ignore them otherwise.
    for key in ("peak_load_kw", "peak_load_mw", "total_network_length_m", "connection_length_m"):
        if key in value:
            result[key] = value[key]
    return result


def _nested_number(value: Mapping[str, Any], parent: str, child: str) -> float | None:
    nested = value.get(parent)
    if isinstance(nested, Mapping):
        return _number_or_none(nested.get(child))
    return None


def _first_number(*values: Any) -> float | None:
    for value in values:
        parsed = _number_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _number_or_none(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _difference(central: Any, decentral: Any) -> float | None:
    central_value = _number_or_none(central)
    decentral_value = _number_or_none(decentral)
    if central_value is None or decentral_value is None:
        return None
    return decentral_value - central_value


def _resource_utilization(
    limits: Mapping[str, Any], supply: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Apply the legacy viewer's potential-limit calculation server-side."""

    resources: dict[str, dict[str, Any]] = {}
    for name, raw_limit in limits.items():
        if not isinstance(raw_limit, Mapping):
            continue
        limit = _number_or_none(raw_limit.get("limit"))
        if limit is None:
            continue
        metric = raw_limit.get("metric")
        used = 0.0
        if name == "biomass":
            boiler = supply.get("biomass_boiler")
            chp = supply.get("biomass_chp")
            boiler_heat = _nested_number_or_zero(boiler, "annual_energy_mwh")
            chp_heat = _nested_number_or_zero(chp, "annual_heat_energy_mwh")
            boiler_efficiency = _number_or_none(raw_limit.get("boiler_efficiency")) or 1.0
            chp_efficiency = _number_or_none(raw_limit.get("chp_eff_electric")) or 1.0
            power_to_heat = _number_or_none(raw_limit.get("chp_power_to_heat_ratio")) or 1.0
            used = boiler_heat / boiler_efficiency + chp_heat / (chp_efficiency * power_to_heat)
        else:
            technology = supply.get(name)
            if metric == "capacity":
                used = _first_number(
                    _nested_value(technology, "capacity_kw"),
                    _nested_value(technology, "capacity_th_kw"),
                    _nested_value(technology, "capacity_el_kw"),
                ) or 0.0
            else:
                used = _first_number(
                    _nested_value(technology, "annual_energy_mwh"),
                    _nested_value(technology, "annual_heat_energy_mwh"),
                ) or 0.0
        resources[str(name)] = {
            "used": used,
            "limit": limit,
            "unit": raw_limit.get("unit"),
            "utilization_pct": used / limit * 100 if limit > 0 else 0.0,
        }
    return resources


def _nested_value(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, Mapping) else None


def _nested_number_or_zero(value: Any, key: str) -> float:
    return _number_or_none(_nested_value(value, key)) or 0.0


def _timeseries_rows(value: Any) -> list[dict[str, Any]] | None:
    """Normalize common JSON time-series encodings into rows."""

    if isinstance(value, list):
        rows = [dict(item) for item in value if isinstance(item, Mapping)]
        return rows or None
    if not isinstance(value, Mapping):
        return None

    for key in ("points", "rows", "data", "timeseries", "time_series"):
        nested = value.get(key)
        if isinstance(nested, list):
            rows = [dict(item) for item in nested if isinstance(item, Mapping)]
            if rows:
                return rows
        if isinstance(nested, Mapping):
            value = nested
            break

    series = value.get("series")
    if not isinstance(series, Mapping):
        # A mapping of named arrays is also a useful and common export shape.
        series = {
            key: item
            for key, item in value.items()
            if isinstance(item, list) and key not in {"timestamps", "time", "dates"}
        }
    if not series or not all(isinstance(item, Sequence) and not isinstance(item, (str, bytes)) for item in series.values()):
        return None

    timestamps = value.get("timestamps", value.get("time", value.get("dates", [])))
    timestamps = list(timestamps) if isinstance(timestamps, Sequence) and not isinstance(timestamps, (str, bytes)) else []
    length = max((len(item) for item in series.values()), default=0)
    rows = []
    for index in range(length):
        row: dict[str, Any] = {}
        if index < len(timestamps):
            row["timestamp"] = timestamps[index]
        for name, values in series.items():
            if index < len(values):
                row[str(name)] = values[index]
        rows.append(row)
    return rows or None


def _read_timeseries_csv(path: Path) -> list[dict[str, Any]] | None:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = []
            for raw in reader:
                row: dict[str, Any] = {}
                for key, value in raw.items():
                    if key is None:
                        continue
                    text = (value or "").strip()
                    if not text:
                        row[key] = None
                        continue
                    try:
                        row[key] = float(text)
                    except ValueError:
                        row[key] = text
                rows.append(row)
            return rows or None
    except (OSError, UnicodeDecodeError, csv.Error):
        return None


def _requested_series(series: str | Sequence[str] | None) -> set[str]:
    if series is None:
        return set()
    values = [series] if isinstance(series, str) else list(series)
    return {part.strip() for value in values for part in value.split(",") if part.strip()}


def _downsample_rows(rows: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
    if len(rows) <= max_points:
        return rows
    if max_points <= 1:
        return [rows[0]]
    # Evenly spaced indices preserve temporal order and always include both
    # endpoints.  This is deterministic and works for mixed numeric/string
    # series without inventing values.
    indices = {
        round(index * (len(rows) - 1) / (max_points - 1))
        for index in range(max_points)
    }
    return [rows[index] for index in sorted(indices)]


def _series_from_rows(rows: list[dict[str, Any]]) -> dict[str, list[Any]]:
    keys = sorted(
        {
            key
            for row in rows
            for key, value in row.items()
            if key not in {"timestamp", "time", "datetime", "date"} and _is_number(value)
        }
    )
    return {key: [row.get(key) for row in rows] for key in keys}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _candidate_id(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


__all__ = ["LegacyResultAdapter"]
