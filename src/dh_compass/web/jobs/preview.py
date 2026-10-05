"""Child-process candidate preview execution.

Preview workers deliberately stop after :func:`prepare_geospatial_data`; no
resource assessment, optimization, or result writing is performed here.  The
worker writes ordinary GeoJSON/JSON artifacts under the configured output root
and communicates state through the metadata database.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import threading
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dh_compass import pipeline
from dh_compass.config import load_config_from_document

from ..persistence.database import create_metadata_engine
from ..persistence.migrations import run_migrations
from ..persistence.repositories import (
    ArtifactMetadataRepository,
    JobEventRepository,
    MetadataNotFound,
    PreviewRepository,
)
from ..settings import WebSettings


class PreviewJobProcessError(RuntimeError):
    """Raised when a preview process cannot be started or is unknown."""


class PreviewCancelled(RuntimeError):
    """Internal cooperative-cancellation signal."""


@dataclass(slots=True)
class _JobHandle:
    process: multiprocessing.Process
    cancel_event: Any


class _EventEmitter:
    def __init__(self, engine, preview_id: str):
        self.events = JobEventRepository(engine)
        self.preview_id = preview_id

    def emit(self, event_type: str, data: Mapping[str, Any] | None = None) -> None:
        self.events.append_ordered(
            self.preview_id,
            "preview",
            event_type,
            _json_safe(dict(data or {})),
        )


def _preview_is_stale(previews: PreviewRepository, preview_id: str) -> bool:
    return previews.get(preview_id)["status"] == "stale"


def _check_cancel(cancel_event: Any) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise PreviewCancelled("Preview cancellation was requested.")


def run_preview_worker(
    database_path: str | Path,
    project_root: str | Path,
    output_root: str | Path,
    preview_id: str,
    scenario_id: str,
    scenario_revision_id: str,
    document: Mapping[str, Any],
    cancel_event: Any = None,
    *,
    allow_building_export: bool = True,
) -> None:
    """Execute one preview in a process with no optimization side effects."""

    settings = WebSettings(
        project_root=project_root,
        metadata_database_path=database_path,
        output_root=output_root,
    )
    engine = create_metadata_engine(settings)
    run_migrations(engine)
    previews = PreviewRepository(engine)
    emitter = _EventEmitter(engine, preview_id)
    try:
        if _preview_is_stale(previews, preview_id):
            emitter.emit("job.status_changed", {"status": "stale"})
            return
        previews.update_status(preview_id, "running", stage="starting", fraction=0.0)
        emitter.emit("job.status_changed", {"status": "running"})
        _check_cancel(cancel_event)

        config = load_config_from_document(
            document,
            project_root=project_root,
            inherit_defaults=False,
        )
        if _preview_is_stale(previews, preview_id):
            emitter.emit("job.status_changed", {"status": "stale"})
            return
        previews.update_status(
            preview_id,
            "running",
            stage="load_inputs",
            completed=0,
            total=3,
            fraction=0.1,
        )
        emitter.emit("pipeline.stage_started", {"stage": "load_inputs"})
        loaded = pipeline.load_inputs(config)
        _check_cancel(cancel_event)
        emitter.emit("pipeline.stage_completed", {"stage": "load_inputs"})

        if _preview_is_stale(previews, preview_id):
            emitter.emit("job.status_changed", {"status": "stale"})
            return
        previews.update_status(
            preview_id,
            "running",
            stage="prepare_geospatial_data",
            completed=1,
            total=3,
            fraction=0.45,
        )
        emitter.emit("pipeline.stage_started", {"stage": "prepare_geospatial_data"})
        prepared = pipeline.prepare_geospatial_data(loaded, config)
        _check_cancel(cancel_event)
        emitter.emit("pipeline.stage_completed", {"stage": "prepare_geospatial_data"})

        if _preview_is_stale(previews, preview_id):
            emitter.emit("job.status_changed", {"status": "stale"})
            return
        previews.update_status(
            preview_id,
            "running",
            stage="export_preview",
            completed=2,
            total=3,
            fraction=0.75,
        )
        emitter.emit("pipeline.stage_started", {"stage": "export_preview"})
        output_path = (
            Path(output_root).expanduser().resolve()
            / ".previews"
            / scenario_id
            / preview_id
        )
        output_path.mkdir(parents=True, exist_ok=True)
        summary, artifacts = _export_preview(
            output_path,
            prepared,
            config,
            scenario_revision_id=scenario_revision_id,
            allow_building_export=allow_building_export,
            cancel_event=cancel_event,
            engine=engine,
            preview_id=preview_id,
        )
        _check_cancel(cancel_event)
        if previews.get(preview_id)["status"] == "stale":
            emitter.emit("job.status_changed", {"status": "stale"})
            return
        previews.set_summary(preview_id, summary)
        emitter.emit("pipeline.stage_completed", {"stage": "export_preview"})
        previews.update_status(
            preview_id,
            "ready",
            stage="complete",
            completed=3,
            total=3,
            fraction=1.0,
        )
        emitter.emit(
            "job.status_changed",
            {"status": "ready", "artifact_count": len(artifacts)},
        )
    except PreviewCancelled as exc:
        try:
            previews.update_status(preview_id, "cancelled", failure_summary=str(exc))
            emitter.emit("job.status_changed", {"status": "cancelled"})
        except Exception:
            # The worker may be cancelled while the metadata database is being
            # shut down.  There is no safe recovery action inside the child.
            pass
    except Exception as exc:  # noqa: BLE001 - worker boundary must persist failures
        message = f"{type(exc).__name__}: {exc}"
        try:
            previews.update_status(preview_id, "failed", failure_summary=message)
            emitter.emit(
                "job.failed",
                {"message": message, "traceback": traceback.format_exc(limit=8)},
            )
        except Exception:
            pass
    finally:
        engine.dispose()


def _export_preview(
    output_path: Path,
    prepared: Any,
    config: Any,
    *,
    scenario_revision_id: str,
    allow_building_export: bool,
    cancel_event: Any,
    engine: Any,
    preview_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    layers = output_path / "layers"
    layers.mkdir(parents=True, exist_ok=True)
    candidate_records = _candidate_records(prepared.subgraph_attributes_df)
    lhd_collection = _graph_features(
        prepared.lhd_graph,
        candidate_lookup=_edge_candidate_lookup(prepared.subgraph_dict),
        layer="lhd",
    )
    candidate_collection = _graph_features(
        prepared.lhd_graph,
        candidate_lookup=_edge_candidate_lookup(prepared.subgraph_dict),
        layer="candidate",
    )
    screened_collection = _screened_out_features(prepared.street_network, prepared.lhd_graph)
    _check_cancel(cancel_event)

    files: list[tuple[str, str, str, dict[str, Any]]] = [
        (
            "candidate_areas.geojson",
            "Candidate areas",
            "application/geo+json",
            candidate_collection,
        ),
        (
            "lhd_edges.geojson",
            "Linear heat density edges",
            "application/geo+json",
            lhd_collection,
        ),
        (
            "screened_out.geojson",
            "Screened-out street edges",
            "application/geo+json",
            screened_collection,
        ),
        ("candidates.json", "Candidate summaries", "application/json", candidate_records),
    ]
    if allow_building_export:
        building_collection = _building_features(prepared.buildings)
        files.append(
            ("buildings.geojson", "Building preview", "application/geo+json", building_collection)
        )

    summary = _preview_summary(
        prepared,
        config,
        candidate_records,
        scenario_revision_id=scenario_revision_id,
        availability={name.rsplit(".", 1)[0]: True for name, _, _, _ in files},
        building_exported=allow_building_export,
        screened_out_count=len(screened_collection.get("features", [])),
    )
    files.append(("preview_summary.json", "Preview summary", "application/json", summary))

    artifact_repository = ArtifactMetadataRepository(engine)
    artifacts: list[dict[str, Any]] = []
    output_root = output_path.parents[2]
    for relative_name, display_name, media_type, value in files:
        _check_cancel(cancel_event)
        path = output_path / relative_name
        path.write_text(
            json.dumps(_json_safe(value), ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        storage_key = path.relative_to(output_root).as_posix()
        checksum = _sha256(path)
        artifact = artifact_repository.create(
            preview_id=preview_id,
            display_name=display_name,
            description=f"Candidate preview artifact: {relative_name}",
            media_type=media_type,
            storage_key=storage_key,
            status="available",
            byte_size=path.stat().st_size,
            checksum_sha256=checksum,
        )
        artifacts.append(artifact)
    return summary, artifacts


def _preview_summary(
    prepared: Any,
    config: Any,
    candidates: list[dict[str, Any]],
    *,
    scenario_revision_id: str,
    availability: Mapping[str, bool],
    building_exported: bool,
    screened_out_count: int,
) -> dict[str, Any]:
    buildings = prepared.buildings
    included_buildings = None
    included_demand = None
    total_demand = None
    try:
        included = buildings[buildings["subgraph_id"].notna()]
        included_buildings = int(len(included))
        included_demand = float(included["heat_demand"].sum())
        total_demand = float(buildings["heat_demand"].sum())
    except (KeyError, TypeError, AttributeError, ValueError):
        pass
    network_length = 0.0
    try:
        network_length = sum(
            float(data.get("length", 0.0))
            for _, _, data in prepared.lhd_graph.edges(data=True)
        )
    except (AttributeError, TypeError, ValueError):
        pass
    excluded_share = None
    if total_demand is not None and total_demand > 0 and included_demand is not None:
        excluded_share = max(0.0, min(100.0, 100.0 * (total_demand - included_demand) / total_demand))
    return {
        "candidate_count": len(candidates),
        "included_buildings": included_buildings,
        "included_demand_mwh": included_demand,
        "network_length_m": network_length,
        "excluded_demand_share_pct": excluded_share,
        "screened_out_edge_count": screened_out_count,
        "input_revision": scenario_revision_id,
        "threshold_mwh_per_m_a": float(config.network.linear_heat_density_threshold),
        "linear_heat_density_threshold_mwh_per_m_a": float(
            config.network.linear_heat_density_threshold
        ),
        "candidate_summaries": candidates,
        "availability": {
            "candidate_areas": True,
            "lhd": True,
            "screened_out": True,
            "buildings": building_exported,
            **dict(availability),
        },
    }


def _candidate_records(attributes: Any) -> list[dict[str, Any]]:
    if attributes is None or not hasattr(attributes, "to_dict"):
        return []
    result: list[dict[str, Any]] = []
    for row in attributes.to_dict(orient="records"):
        candidate_id = _int_value(row.get("Subgraph ID"))
        if candidate_id is None:
            continue
        result.append(
            {
                "id": candidate_id,
                "annual_heat_demand_mwh": _float_value(row.get("Annual Heat Demand [MWh/a]")),
                "average_linear_heat_density_mwh_per_m_a": _float_value(
                    row.get("Average Linear Heat Density [MWh/m/a]")
                ),
                "total_network_length_m": _float_value(row.get("Total network length [m]")),
                "buildings": _int_value(row.get("Total building count")),
                "peak_load_mw": _float_value(row.get("Peak Load [MW]")),
                "properties": {
                    "total_distribution_pipe_cost_eur": _float_value(
                        row.get("Total distribution pipe cost [€]")
                    ),
                    "total_building_connection_cost_eur": _float_value(
                        row.get("Total building connection cost [€]")
                    ),
                    "total_transfer_station_cost_eur": _float_value(
                        row.get("Total transfer station cost [€]")
                    ),
                },
            }
        )
    return result


def _edge_candidate_lookup(subgraphs: Mapping[Any, Any]) -> dict[tuple[Any, Any, Any], int]:
    lookup: dict[tuple[Any, Any, Any], int] = {}
    for candidate_id, graph in subgraphs.items():
        try:
            iterator = graph.edges(keys=True)
        except TypeError:
            iterator = ((left, right, 0) for left, right in graph.edges())
        for left, right, key in iterator:
            value = _int_value(candidate_id)
            if value is None:
                continue
            lookup[(left, right, key)] = value
            lookup[(right, left, key)] = value
            lookup[(left, right, 0)] = value
            lookup[(right, left, 0)] = value
    return lookup


def _graph_features(graph: Any, *, candidate_lookup: Mapping[tuple[Any, Any, Any], int], layer: str) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    if graph is None or not hasattr(graph, "edges"):
        return {"type": "FeatureCollection", "features": features}
    try:
        edges = graph.edges(keys=True, data=True)
    except TypeError:
        edges = ((left, right, 0, data) for left, right, data in graph.edges(data=True))
    for index, (left, right, key, data) in enumerate(edges):
        geometry = _edge_geometry(graph, left, right, data)
        if geometry is None:
            continue
        candidate_id = candidate_lookup.get((left, right, key))
        properties = {
            "layer": layer,
            "candidate_id": candidate_id,
            "linear_heat_density": _float_value(data.get("linear_heat_density")),
            "heat_demand_mwh": _float_value(data.get("heat_demand")),
            "length_m": _float_value(data.get("length")),
        }
        features.append(
            {
                "type": "Feature",
                "id": f"{layer}-{index}",
                "geometry": geometry,
                "properties": properties,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _screened_out_features(network: Any, lhd_graph: Any) -> dict[str, Any]:
    included: set[tuple[Any, Any, Any]] = set()
    if lhd_graph is not None and hasattr(lhd_graph, "edges"):
        try:
            edges = lhd_graph.edges(keys=True)
        except TypeError:
            edges = ((left, right, 0) for left, right in lhd_graph.edges())
        for left, right, key in edges:
            included.add((left, right, key))
            included.add((right, left, key))
    features: list[dict[str, Any]] = []
    if network is None or not hasattr(network, "edges"):
        return {"type": "FeatureCollection", "features": features}
    try:
        edges = network.edges(keys=True, data=True)
    except TypeError:
        edges = ((left, right, 0, data) for left, right, data in network.edges(data=True))
    for index, (left, right, key, data) in enumerate(edges):
        if (left, right, key) in included or (left, right, 0) in included:
            continue
        geometry = _edge_geometry(network, left, right, data)
        if geometry is None:
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"screened-out-{index}",
                "geometry": geometry,
                "properties": {"layer": "screened_out", "screened_out": True},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _edge_geometry(graph: Any, left: Any, right: Any, data: Mapping[str, Any]) -> dict[str, Any] | None:
    geometry = data.get("geometry")
    if geometry is not None:
        try:
            from shapely.geometry import mapping

            return _json_safe(mapping(geometry))
        except (TypeError, ValueError):
            if isinstance(geometry, Mapping):
                return _json_safe(dict(geometry))
    try:
        left_data = graph.nodes[left]
        right_data = graph.nodes[right]
        return {
            "type": "LineString",
            "coordinates": [
                [float(left_data["x"]), float(left_data["y"])],
                [float(right_data["x"]), float(right_data["y"])],
            ],
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _building_features(buildings: Any) -> dict[str, Any]:
    try:
        frame = buildings.to_crs(4326) if getattr(buildings, "crs", None) else buildings
        document = json.loads(frame.to_json(drop_id=False))
        for index, feature in enumerate(document.get("features", [])):
            properties = feature.setdefault("properties", {})
            properties["building_id"] = str(feature.get("id") or index)
            value = properties.get("subgraph_id")
            properties["screened_out"] = value is None
        return _json_safe(document)
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return {"type": "FeatureCollection", "features": []}


def _int_value(value: Any) -> int | None:
    try:
        if value is None:
            return None
        result = int(value)
        return result
    except (TypeError, ValueError, OverflowError):
        return None


def _float_value(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
        return result if result == result else None
    except (TypeError, ValueError, OverflowError):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class PreviewJobManager:
    """Own child processes while the API process is alive."""

    def __init__(self, settings: WebSettings):
        self.settings = settings
        self._jobs: dict[str, _JobHandle] = {}
        self._lock = threading.RLock()

    def start(
        self,
        *,
        preview_id: str,
        scenario_id: str,
        scenario_revision_id: str,
        document: Mapping[str, Any],
        worker_target: Callable[..., Any] = run_preview_worker,
    ) -> None:
        with self._lock:
            if preview_id in self._jobs:
                raise PreviewJobProcessError(f"Preview {preview_id} is already running.")
            context = multiprocessing.get_context("spawn")
            cancel_event = context.Event()
            process = context.Process(
                target=worker_target,
                args=(
                    self.settings.metadata_database_path,
                    self.settings.project_root,
                    self.settings.output_root,
                    preview_id,
                    scenario_id,
                    scenario_revision_id,
                    dict(document),
                    cancel_event,
                ),
                name=f"dh-compass-preview-{preview_id}",
                daemon=True,
            )
            try:
                process.start()
            except (OSError, RuntimeError) as exc:
                raise PreviewJobProcessError("The preview worker could not be started.") from exc
            self._jobs[preview_id] = _JobHandle(process=process, cancel_event=cancel_event)
            watcher = threading.Thread(
                target=self._watch,
                args=(preview_id, process),
                name=f"watch-preview-{preview_id}",
                daemon=True,
            )
            watcher.start()

    def cancel(self, preview_id: str) -> bool:
        with self._lock:
            handle = self._jobs.get(preview_id)
            if handle is None:
                return False
            handle.cancel_event.set()
            return True

    def is_running(self, preview_id: str) -> bool:
        with self._lock:
            handle = self._jobs.get(preview_id)
            return bool(handle and handle.process.is_alive())

    def _watch(self, preview_id: str, process: multiprocessing.Process) -> None:
        process.join()
        with self._lock:
            self._jobs.pop(preview_id, None)
        engine = None
        try:
            settings = self.settings
            engine = create_metadata_engine(settings)
            run_migrations(engine)
            repository = PreviewRepository(engine)
            current = repository.get(preview_id)
            if current["status"] in {"queued", "running", "cancellation_requested"}:
                message = (
                    "The preview worker exited without reporting a final state"
                    if process.exitcode == 0
                    else f"The preview worker stopped unexpectedly (exit code {process.exitcode})."
                )
                repository.update_status(preview_id, "failed", failure_summary=message)
                JobEventRepository(engine).append_ordered(
                    preview_id,
                    "preview",
                    "job.failed",
                    {"message": message},
                )
        except (MetadataNotFound, Exception):
            # API shutdown or a deleted scenario should not crash the watcher.
            pass
        finally:
            if engine is not None:
                engine.dispose()


__all__ = ["PreviewJobManager", "PreviewJobProcessError", "run_preview_worker"]
