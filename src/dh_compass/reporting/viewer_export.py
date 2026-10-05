import json
from pathlib import Path

import pandas as pd
from shapely.geometry import LineString, mapping

from dh_compass.config import AppConfig, PathConfig
from dh_compass.optimization.context import OptimizationContext
from dh_compass.reporting.attribution import OSM_PROVENANCE, with_map_provenance
from dh_compass.reporting.costs import build_cost_breakdown
from dh_compass.reporting.json_export import to_native
from dh_compass.reporting.portfolio import portfolio_from_stored_result
from dh_compass.reporting.result_schema import _get_val


def _edge_to_feature(u, v, key, data, street_network):
    geom = data.get("geometry")
    if geom is None:
        p_u = street_network.nodes[u]
        p_v = street_network.nodes[v]
        geom = LineString([(p_u["x"], p_u["y"]), (p_v["x"], p_v["y"])])
    return {
        "type": "Feature",
        "geometry": mapping(geom),
        "properties": {
            "u": int(u),
            "v": int(v),
            "key": int(key),
            "length_m": round(data.get("length", 0), 2),
            "heat_demand_mwh": round(data.get("heat_demand", 0), 4),
            "peak_load_kw": round(data.get("peak_load", 0), 4),
            "linear_heat_density": round(data.get("linear_heat_density", 0), 4),
            "building_count": int(data.get("building_count_edge", 0)),
        },
    }


def _path_nodes_to_geojson(path_nodes, street_network):
    if not path_nodes or len(path_nodes) < 2:
        return None
    coords = []
    for nid in path_nodes:
        if nid in street_network.nodes:
            n = street_network.nodes[nid]
            coords.append((n["x"], n["y"]))
    if len(coords) < 2:
        return None
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {"type": "connection_path"},
            }
        ],
    }


def _build_potential_limits(ctx: OptimizationContext) -> dict[str, object]:
    """Build viewer limits from typed resource and technology inputs."""

    limits: dict[str, object] = {}
    resources = ctx.resources
    central = ctx.technologies.central

    def available(technology_name: str, limit: float) -> bool:
        return limit > 0 and any(
            bool(definition.get("on_off", 0))
            for definition in getattr(central, technology_name).values()
        )

    industrial_limit = resources.industrial_eh_energy_limit_mwh
    if available("industrial_eh", industrial_limit):
        limits["industrial_excess_heat"] = {
            "limit": round(industrial_limit, 2),
            "unit": "MWh",
            "metric": "energy",
        }

    biomass_limit = resources.biomass_energy_limit_mwh
    if available("biomass_boiler", biomass_limit) or available("biomass_chp", biomass_limit):
        bm_boiler_eff = central.biomass_boiler[0].get("efficiency", 1.0)
        bm_chp = central.biomass_chp[0]
        limits["biomass"] = {
            "limit": round(biomass_limit, 2),
            "unit": "MWh",
            "metric": "energy",
            "shared_techs": ["biomass_boiler", "biomass_chp"],
            "boiler_efficiency": bm_boiler_eff,
            "chp_eff_electric": bm_chp.get("efficiency_electric", 1.0),
            "chp_power_to_heat_ratio": bm_chp.get("power_to_heat_ratio", 1.0),
        }

    for technology_name, key, limit in (
        ("waste_to_energy", "waste_to_energy", resources.wte_energy_limit_mwh),
        ("geothermal", "geothermal", resources.geothermal_energy_limit_mwh),
        ("river_heat_pump", "river_heat_pump", resources.river_hp_capacity_limit_kw),
        ("wwtp_heat_pump", "wwtp_heat_pump", resources.wwtp_hp_capacity_limit_kw),
    ):
        if available(technology_name, limit):
            limits[key] = {
                "limit": round(limit, 2),
                "unit": "kW" if "heat_pump" in key else "MWh",
                "metric": "capacity" if "heat_pump" in key else "energy",
            }
    return limits


def _build_lhd_geojson(optimizer, lhd_graph, street_network):
    edge_to_sg = {}
    for sg_id, sg in optimizer.subgraph_dict.items():
        for u, v, k in sg.edges(keys=True):
            edge_to_sg[(u, v, k)] = sg_id

    features = []
    for u, v, key, data in lhd_graph.edges(keys=True, data=True):
        feat = _edge_to_feature(u, v, key, data, street_network)
        feat["properties"]["subgraph_id"] = int(edge_to_sg.get((u, v, key), -1))
        features.append(feat)
    return {"type": "FeatureCollection", "features": features}


def export_viewer_data(
    optimizer,
    optimization_results,
    street_network,
    lhd_graph,
    config: AppConfig,
) -> dict[str, object]:
    ctx = optimizer.ctx
    attrs = optimizer.subgraph_attributes_df

    viewer_config = {
        "case": config.scenario.case,
        "dt": float(ctx.market.central.dt),
        "flh": config.network.flh,
        "lhd_threshold": config.network.linear_heat_density_threshold,
        "investment_period_years": ctx.economic.investment_duration,
        "interest_rate": ctx.economic.interest_rate,
        "infrastructure_cost_factor": ctx.network.infrastructure_cost_factor,
    }

    connected_ids = list(optimizer.connected_subgraphs)
    all_ids = [r.subgraph_id for r in optimization_results]
    disconnected_ids = [sid for sid in all_ids if sid not in connected_ids]

    connected_demand = sum(
        _get_val(attrs.loc[sid, "Annual Heat Demand [MWh/a]"]) for sid in connected_ids
    )
    disconnected_demand = sum(
        _get_val(attrs.loc[sid, "Annual Heat Demand [MWh/a]"])
        for sid in disconnected_ids
    )
    total_demand = connected_demand + disconnected_demand

    summary = {
        "total_subgraphs": len(all_ids),
        "connected_subgraphs": len(connected_ids),
        "disconnected_subgraphs": len(disconnected_ids),
        "total_heat_demand_mwh": round(total_demand, 4),
        "connected_heat_demand_mwh": round(connected_demand, 4),
        "disconnected_heat_demand_mwh": round(disconnected_demand, 4),
        "connected_share_pct": round(connected_demand / total_demand * 100, 2)
        if total_demand > 0
        else 0,
    }

    iterations = []
    for step_info in optimizer.iteration_history:
        sg_id = step_info.subgraph_id

        cumulative_supply = None
        if step_info.decision == "connected" and sg_id in optimizer.opt_results_central:
            cumulative_supply = portfolio_from_stored_result(
                optimizer.opt_results_central[sg_id]
            )

        connecting_path_geojson = _path_nodes_to_geojson(
            step_info.connecting_path_nodes, street_network
        )

        iterations.append(
            {
                "step": step_info.step,
                "subgraph_id": sg_id,
                "decision": step_info.decision,
                "central_cost_total": step_info.central_cost_total,
                "previous_central_cost": step_info.previous_central_cost,
                "marginal_central_cost": step_info.marginal_central_cost,
                "decentral_cost": step_info.decentral_cost,
                "grid_cost_raw": step_info.grid_cost_raw,
                "connection_length_m": step_info.connection_length_m,
                "cumulative_connected_ids": step_info.cumulative_connected_ids,
                "cumulative_supply": cumulative_supply,
                "connecting_path_geojson": connecting_path_geojson,
            }
        )

    subgraphs = {}
    for result in optimization_results:
        sg_id = result.subgraph_id
        row = attrs.loc[sg_id]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]

        sg = optimizer.subgraph_dict[sg_id]
        edge_features = [
            _edge_to_feature(u, v, key, data, street_network)
            for u, v, key, data in sg.edges(keys=True, data=True)
        ]

        portfolio = None
        cost_breakdown = None
        if sg_id in optimizer.opt_results_central:
            portfolio = portfolio_from_stored_result(
                optimizer.opt_results_central[sg_id]
            )
            cost_breakdown = build_cost_breakdown(
                portfolio, ctx, decentral_bool=False
            )

        cluster_details = optimizer.cluster_details.get(sg_id, {})
        clusters_list = []
        for cid, cinfo in sorted(cluster_details.items()):
            c_entry = {
                "cluster_id": int(cid),
                "n_buildings": int(cinfo.get("n_buildings", 0)),
                "centroid_demand_mwh": round(
                    float(cinfo.get("centroid_demand", 0)), 4
                ),
                "total_demand_mwh": round(float(cinfo.get("total_demand", 0)), 4),
                "unscaled_annualized_cost_eur": round(
                    float(cinfo.get("cost", 0)), 2
                ),
                "scaled_annualized_cost_eur": round(
                    float(cinfo.get("scaled_cost", 0)), 2
                ),
            }
            c_portfolio = cinfo.get("portfolio")
            if c_portfolio:
                c_entry["supply"] = c_portfolio.get("supply", {})
                c_entry["storage"] = c_portfolio.get("storage", {})
            clusters_list.append(c_entry)

        sg_demand = _get_val(row["Annual Heat Demand [MWh/a]"])
        sg_buildings = int(_get_val(row["Total building count"]))
        sg_peak_load_kw = _get_val(row["Peak Load [MW]"]) * 1000
        sg_network_length = _get_val(row["Total network length [m]"])
        sg_avg_lhd = _get_val(row["Average Linear Heat Density [MWh/m/a]"])

        entry = {
            "is_connected": result.is_connected,
            "annual_heat_demand_mwh": round(sg_demand, 4),
            "peak_load_kw": round(sg_peak_load_kw, 4),
            "buildings": sg_buildings,
            "total_network_length_m": round(sg_network_length, 2),
            "avg_lhd": round(sg_avg_lhd, 4),
            "central_cost": round(float(result.central_cost), 2),
            "decentral_cost": round(float(result.decentral_cost), 2),
            "central_grid_cost_raw": round(float(result.grid_cost), 2),
            "connection_length_m": round(float(result.connection_length), 2),
            "edges_geojson": {
                "type": "FeatureCollection",
                "features": edge_features,
            },
            "clusters": clusters_list,
        }
        if portfolio:
            entry["supply"] = portfolio.get("supply", {})
            entry["storage"] = portfolio.get("storage", {})
            entry["total_heat_production_mwh"] = portfolio.get(
                "total_heat_production_mwh", 0
            )
            entry["cost_breakdown"] = cost_breakdown

        subgraphs[str(sg_id)] = entry

    potential_limits = _build_potential_limits(ctx)

    lhd_geojson = _build_lhd_geojson(optimizer, lhd_graph, street_network)

    return {
        "config": viewer_config,
        "summary": summary,
        "iterations": iterations,
        "subgraphs": subgraphs,
        "potential_limits": potential_limits,
        "lhd_edges_geojson": lhd_geojson,
    }


def save_viewer_data(
    data: dict[str, object],
    filepath: str | Path,
    *,
    template_path: str | Path | None = None,
) -> None:
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    serializable_data = with_map_provenance(to_native(data))
    serializable_data.setdefault("map_source_provenance", dict(OSM_PROVENANCE))
    with filepath.open("w", encoding="utf-8") as f:
        json.dump(serializable_data, f, indent=2, ensure_ascii=False)

    template_path = Path(template_path or PathConfig.from_project_root().viewer_template)
    if not template_path.exists():
        return

    template = template_path.read_text(encoding="utf-8")
    # Older custom templates must never receive private server credentials.
    template = template.replace("__CARTO_API_KEY__", "")

    compact_json = json.dumps(serializable_data, ensure_ascii=False)
    data_tag_open = '<script type="application/json" id="viewer-data">'
    data_tag_close = "</script>"
    html = template.replace(
        "</body>", f"{data_tag_open}{compact_json}{data_tag_close}\n</body>", 1
    )
    out_html = filepath.with_suffix(".html")
    out_html.write_text(html, encoding="utf-8")
