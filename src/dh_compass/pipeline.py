"""Application pipeline for a heat-grid planning run."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import networkx as nx

from dh_compass.config import (
    AppConfig,
    PreparedGeospatialData,
    ResourceAvailability,
    RunArtifacts,
    TimeSeriesData,
    load_default_config,
)
from dh_compass.demand.runtime import build_subgraph_profile_generator, load_time_series
from dh_compass.observability.progress import (
    CancellationRequested,
    CancellationToken,
    PipelineObserver,
    check_cancellation,
    emit_progress,
)
from dh_compass.optimization.context import (
    OptimizationContext,
    OptimizationResult,
    build_optimization_context,
)
from dh_compass.optimization.orchestration import HeatGridOptimizer
from dh_compass.preprocessing.candidate_areas import build_candidate_areas, order_subgraphs
from dh_compass.preprocessing.heat_density import add_edge_heat_demand
from dh_compass.resources.assessment import assess_heat_resources


class PipelineInputs(TypedDict):
    """External inputs shared by the preparation stages of one run."""

    buildings: object
    bbox: object
    street_network: nx.Graph
    time_series: TimeSeriesData


def load_inputs(config: AppConfig) -> PipelineInputs:
    """Load external geospatial data and the reference time series."""

    from dh_compass.preprocessing.buildings import load_buildings
    from dh_compass.preprocessing.street_network import download_street_network

    buildings, bbox = load_buildings(config)
    street_network = download_street_network(config)
    time_series = load_time_series(config.paths, config)
    return {
        "buildings": buildings,
        "bbox": bbox,
        "street_network": street_network,
        "time_series": time_series,
    }


def prepare_geospatial_data(
    inputs: PipelineInputs, config: AppConfig
) -> PreparedGeospatialData:
    """Map buildings, calculate LHD, and construct candidate areas."""

    from dh_compass.preprocessing.buildings import map_buildings_to_edges

    buildings = map_buildings_to_edges(inputs["buildings"], inputs["street_network"])
    street_network = add_edge_heat_demand(
        buildings, inputs["street_network"], config.network.flh
    )
    profile_generator = build_subgraph_profile_generator(
        config.paths, config, temperature_data=inputs["time_series"].data
    )
    lhd_graph, subgraph_dict, attributes = build_candidate_areas(
        buildings,
        street_network,
        config,
        building_profile_generator=profile_generator,
    )
    return PreparedGeospatialData(
        buildings=buildings,
        street_network=street_network,
        lhd_graph=lhd_graph,
        subgraph_dict=subgraph_dict,
        subgraph_attributes_df=attributes,
    )


def optimize_heat_grid(
    prepared: PreparedGeospatialData,
    context: OptimizationContext,
    config: AppConfig,
    *,
    observer: PipelineObserver | None = None,
    cancellation_token: CancellationToken | None = None,
) -> tuple[HeatGridOptimizer, list[OptimizationResult]]:
    """Run the selected candidate ordering and optimization workflow.

    Progress and cancellation are optional application-boundary concerns.  No
    observer or token means the same optimization services and solver calls are
    used as in the command-line workflow.
    """

    optimizer = HeatGridOptimizer(
        context=context,
        street_network=prepared.street_network,
        subgraph_dict=dict(prepared.subgraph_dict),
        subgraph_attributes_df=prepared.subgraph_attributes_df,
        observer=observer,
        cancellation_token=cancellation_token,
        highs_central_lp_method=config.optimization.highs_central_lp_method,
        highs_decentral_lp_method=config.optimization.highs_decentral_lp_method,
        reuse_models=config.optimization.reuse_models,
    )
    ids = order_subgraphs(
        prepared.street_network,
        prepared.subgraph_dict,
        prepared.subgraph_attributes_df,
        config.optimization.subgraph_order,
    )
    check_cancellation(cancellation_token)
    if not ids:
        return optimizer, []
    if config.optimization.subgraph_order == "distance_greedy":
        results = optimizer.run_greedy(ids, max_workers=config.optimization.max_workers)
    else:
        results = optimizer.run(ids, max_workers=config.optimization.max_workers)
    return optimizer, results


def write_outputs(
    optimizer: HeatGridOptimizer,
    optimization_results: list[OptimizationResult],
    prepared: PreparedGeospatialData,
    config: AppConfig,
    *,
    output_dir: str | Path | None = None,
    weather_metadata: Mapping[str, object] | None = None,
) -> tuple[Path, Mapping[str, object], Mapping[str, object]]:
    """Write JSON, charts, viewer data, and network layers for a run."""

    from dh_compass.reporting.attribution import OSM_PROVENANCE
    from dh_compass.reporting.charts import generate_all_charts
    from dh_compass.reporting.json_export import build_full_results_json, save_full_results_json
    from dh_compass.reporting.viewer_export import export_viewer_data, save_viewer_data

    if output_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = config.output.output_root / config.case / stamp
    else:
        output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    full_results = build_full_results_json(
        optimizer, optimization_results, flh=config.network.flh
    )
    full_results["map_source_provenance"] = dict(OSM_PROVENANCE)
    save_full_results_json(dict(OSM_PROVENANCE), output_path / "data_provenance.json")
    if weather_metadata:
        full_results["weather"] = dict(weather_metadata)
        save_full_results_json(dict(weather_metadata), output_path / "weather_provenance.json")
    save_full_results_json(full_results, output_path / "full_results.json")
    generate_all_charts(full_results, str(output_path))

    viewer_data = export_viewer_data(
        optimizer=optimizer,
        optimization_results=optimization_results,
        street_network=prepared.street_network,
        lhd_graph=prepared.lhd_graph,
        config=config,
    )
    save_viewer_data(viewer_data, output_path / "viewer_data.json", template_path=config.paths.viewer_template)

    optimizer.perf.add_optimization_metric(
        "total_buildings_lhd", int(len(prepared.buildings))
    )
    optimizer.perf.save_to_json(output_path / "performance_metrics.json")

    # GeoJSON export is deliberately kept here, at the reporting boundary.
    try:
        _write_network_geojson(prepared, optimizer, optimization_results, output_path)
    except (ImportError, ValueError, KeyError):
        # A JSON-only run should still be useful with a minimal in-memory graph.
        pass
    return output_path, full_results, viewer_data


def _write_network_geojson(
    prepared: PreparedGeospatialData,
    optimizer: HeatGridOptimizer,
    optimization_results: list[OptimizationResult],
    output_path: Path,
) -> None:
    import geopandas as gpd
    from shapely.geometry import LineString

    from dh_compass.network.routing import create_combined_graph

    connected_ids = [result.subgraph_id for result in optimization_results if result.is_connected]
    combined_graph = create_combined_graph(connected_ids, prepared.subgraph_dict)
    connecting_edges = set()
    for path in optimizer.connecting_edges_df.get("path", []):
        for left, right in zip(path, path[1:]):
            connecting_edges.update(((left, right), (right, left)))

    def records(graph: nx.Graph, edge_type: str) -> list[dict[str, object]]:
        result = []
        for u, v, key, data in graph.edges(keys=True, data=True):
            geometry = data.get("geometry")
            if geometry is None:
                geometry = LineString(
                    [(prepared.street_network.nodes[u]["x"], prepared.street_network.nodes[u]["y"]),
                     (prepared.street_network.nodes[v]["x"], prepared.street_network.nodes[v]["y"])]
                )
            result.append({"u": u, "v": v, "geometry": geometry, "type": edge_type})
        return result

    crs = prepared.street_network.graph.get("crs", "EPSG:4326")
    gpd.GeoDataFrame(records(combined_graph, "core"), geometry="geometry", crs=crs).to_crs(4326).to_file(
        output_path / "final_network.geojson", driver="GeoJSON"
    )
    gpd.GeoDataFrame(
        records(prepared.lhd_graph, "candidate"), geometry="geometry", crs=crs
    ).to_crs(4326).to_file(output_path / "lhd_graph.geojson", driver="GeoJSON")
    from dh_compass.reporting.attribution import with_map_provenance

    for name in ("final_network.geojson", "lhd_graph.geojson"):
        path = output_path / name
        document = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(with_map_provenance(document)), encoding="utf-8")


def run_pipeline(
    config: AppConfig | None = None,
    *,
    inputs: PipelineInputs | None = None,
    resources: ResourceAvailability | None = None,
    output_dir: str | Path | None = None,
    observer: PipelineObserver | None = None,
    cancellation_token: CancellationToken | None = None,
) -> RunArtifacts:
    """Run all application stages in dependency order.

    ``observer`` and ``cancellation_token`` are intentionally optional.  The
    pipeline remains usable by the CLI and existing library callers without
    constructing web objects or changing solver behaviour.
    """

    config = config or load_default_config()
    config.paths.cache_root.mkdir(parents=True, exist_ok=True)

    def stage(name: str, operation, **data):
        check_cancellation(cancellation_token)
        emit_progress(observer, "pipeline.stage_started", {"stage": name, **data})
        try:
            result = operation()
        except CancellationRequested:
            raise
        except Exception as exc:
            emit_progress(
                observer,
                "pipeline.stage_failed",
                {"stage": name, "error": f"{type(exc).__name__}: {exc}"},
            )
            raise
        check_cancellation(cancellation_token)
        emit_progress(observer, "pipeline.stage_completed", {"stage": name, **data})
        return result

    loaded = stage(
        "load_inputs",
        lambda: dict(inputs or load_inputs(config)),
        provided=bool(inputs),
    )
    prepared = stage(
        "prepare_geospatial_data",
        lambda: prepare_geospatial_data(loaded, config),
    )
    resource_availability = stage(
        "assess_heat_resources",
        lambda: resources if resources is not None else assess_heat_resources(config, loaded["bbox"]),
    )
    context = stage(
        "build_optimization_context",
        lambda: build_optimization_context(
            config, loaded["time_series"], resource_availability
        ),
    )

    check_cancellation(cancellation_token)
    emit_progress(observer, "pipeline.stage_started", {"stage": "optimize_heat_grid"})
    try:
        if observer is None and cancellation_token is None:
            # Keep the historical call shape for integrations that replace the
            # function in tests or downstream applications.
            optimizer, optimization_results = optimize_heat_grid(
                prepared, context, config
            )
        else:
            optimizer, optimization_results = optimize_heat_grid(
                prepared,
                context,
                config,
                observer=observer,
                cancellation_token=cancellation_token,
            )
    except CancellationRequested:
        raise
    except Exception as exc:
        emit_progress(
            observer,
            "pipeline.stage_failed",
            {"stage": "optimize_heat_grid", "error": f"{type(exc).__name__}: {exc}"},
        )
        raise
    check_cancellation(cancellation_token)
    emit_progress(observer, "pipeline.stage_completed", {"stage": "optimize_heat_grid"})

    written_dir, full_results, viewer_data = stage(
        "write_outputs",
        lambda: write_outputs(
            optimizer,
            optimization_results,
            prepared,
            config,
            output_dir=output_dir,
            **(
                {"weather_metadata": loaded["time_series"].data.attrs["weather"]}
                if isinstance(loaded["time_series"], TimeSeriesData)
                and loaded["time_series"].data.attrs.get("weather")
                else {}
            ),
        ),
    )
    emit_progress(
        observer,
        "pipeline.completed",
        {"output_dir": str(written_dir), "optimization_results": len(optimization_results)},
    )
    return RunArtifacts(
        config=config,
        prepared=prepared,
        resources=resource_availability,
        optimizer=optimizer,
        optimization_results=optimization_results,
        output_dir=written_dir,
        full_results=full_results,
        viewer_data=viewer_data,
    )


__all__ = [
    "CancellationToken",
    "PipelineObserver",
    "PipelineInputs",
    "load_inputs",
    "optimize_heat_grid",
    "prepare_geospatial_data",
    "run_pipeline",
    "write_outputs",
]
