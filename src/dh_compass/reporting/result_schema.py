"""Assembly of the stable full-results reporting schema.

This module works with value-only optimization results and assembles the public
JSON shape.  Cost calculations live in :mod:`dh_compass.reporting.costs`,
portfolio normalization lives in :mod:`dh_compass.reporting.portfolio`, and
native-type conversion/persistence lives in :mod:`dh_compass.reporting.json_export`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..economics.annuity import annuity_factor
from ..optimization.context import OptimizationResult
from ..optimization.orchestration import HeatGridOptimizer
from .costs import build_cost_breakdown
from .portfolio import (
    aggregate_supply_energy,
    portfolio_energy_mwh,
    portfolio_from_stored_result,
    result_frame_from_stored_result,
)


def _get_val(value: object) -> float:
    if hasattr(value, "iloc"):
        return float(value.iloc[0])
    return float(value)


def _require_result_frame(stored_solution: object):
    """Return reportable time-series results or raise a clear contract error."""

    result_frame = result_frame_from_stored_result(stored_solution)
    if result_frame is None:
        raise ValueError(
            "Cannot assemble full results from a ModelSolution without result_df; "
            "run the central model with gathered results enabled."
        )
    return result_frame


def _sum_demand(attrs, ids) -> float:
    if not ids:
        return 0.0
    return sum(_get_val(attrs.loc[subgraph_id, "Annual Heat Demand [MWh/a]"]) for subgraph_id in ids)


def _sum_attr(attrs, ids, column: str) -> float:
    if not ids:
        return 0.0
    return sum(_get_val(attrs.loc[subgraph_id, column]) for subgraph_id in ids)


def _get_list(attrs_row, column: str) -> list[object]:
    value = attrs_row[column]
    if isinstance(value, list):
        return value
    if hasattr(value, "iloc"):
        value = value.iloc[0]
    if isinstance(value, list):
        return value
    return []


def _extract_edges(subgraph) -> list[dict[str, object]]:
    edges = []
    for u, v, key, data in subgraph.edges(keys=True, data=True):
        edges.append(
            {
                "u": u,
                "v": v,
                "key": key,
                "length_m": round(data.get("length", 0), 2),
                "heat_demand_mwh": round(data.get("heat_demand", 0), 4),
                "peak_load_kw": round(data.get("peak_load", 0), 4),
                "linear_heat_density_mwh_per_m_a": round(
                    data.get("linear_heat_density", 0), 4
                ),
                "building_count": int(data.get("building_count_edge", 0)),
            }
        )
    return edges


def assemble_full_results(
    optimizer: HeatGridOptimizer,
    optimization_results: Sequence[OptimizationResult],
    flh: float = 3000,
) -> dict[str, object]:
    """Assemble the documented full-results structure from domain results."""

    ctx = optimizer.ctx
    dt = ctx.market.central.dt
    af = annuity_factor(
        ctx.economic.interest_rate,
        ctx.economic.investment_duration,
    )
    attrs = optimizer.subgraph_attributes_df

    connected_ids = list(optimizer.connected_subgraphs)
    all_ids = [result.subgraph_id for result in optimization_results]
    disconnected_ids = [subgraph_id for subgraph_id in all_ids if subgraph_id not in connected_ids]

    connected_demand = _sum_demand(attrs, connected_ids)
    disconnected_demand = _sum_demand(attrs, disconnected_ids)
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

    combined_graph = None
    if connected_ids:
        last_id = connected_ids[-1]
        stored_solution = optimizer.opt_results_central[last_id]
        result_df = _require_result_frame(stored_solution)
        portfolio = portfolio_from_stored_result(stored_solution)

        grid_raw = optimizer.grid_cost_cumulative
        grid_ann = grid_raw * (1 - ctx.network.residual_value_factor_pipeline) * af
        supply_ann = optimizer.total_cost_central_cumulative - grid_ann
        total_ann = optimizer.total_cost_central_cumulative

        total_buildings = int(_sum_attr(attrs, connected_ids, "Total building count"))

        dist_pipes = _sum_attr(attrs, connected_ids, "Total distribution pipe cost [€]")
        bldg_conn = _sum_attr(attrs, connected_ids, "Total building connection cost [€]")
        xfer_stn = _sum_attr(attrs, connected_ids, "Total transfer station cost [€]")
        pipeline_conn = float(
            optimizer.connecting_edges_df["path_length"].sum()
            * ctx.network.pipeline_cost_per_m
        )

        grid_ann_ratio = (1 - ctx.network.residual_value_factor_pipeline) * af
        cost_breakdown = build_cost_breakdown(portfolio, ctx, decentral_bool=False)

        peak_load_kw = float(result_df["demand_heat"].max())
        all_edges = []
        for subgraph_id in connected_ids:
            all_edges.extend(_extract_edges(optimizer.subgraph_dict[subgraph_id]))

        combined_graph = {
            "connected_subgraph_ids": [int(value) for value in connected_ids],
            "annual_heat_demand_mwh": round(connected_demand, 4),
            "total_buildings": total_buildings,
            "peak_load_kw": round(peak_load_kw, 4),
            "total_network_length_m": round(sum(edge["length_m"] for edge in all_edges), 2),
            "connection_length_m": round(
                float(optimizer.connecting_edges_df["path_length"].sum()), 2
            ),
            "supply": portfolio["supply"],
            "storage": portfolio["storage"],
            "total_heat_production_mwh": portfolio["total_heat_production_mwh"],
            "cost": {
                "total_annualized_eur": round(total_ann, 2),
                "supply_annualized_eur": round(supply_ann, 2),
                "grid_annualized_eur": round(grid_ann, 2),
                "supply_share_pct": round(supply_ann / total_ann * 100, 2)
                if total_ann > 0
                else 0,
                "grid_share_pct": round(grid_ann / total_ann * 100, 2)
                if total_ann > 0
                else 0,
                "supply_breakdown": cost_breakdown,
                "grid_breakdown": {
                    "total_annualized_eur": round(grid_ann, 2),
                    "raw_total_eur": round(grid_raw, 2),
                    "distribution_pipes_eur": round(
                        dist_pipes * grid_ann_ratio, 2
                    ),
                    "building_connections_eur": round(
                        bldg_conn * grid_ann_ratio, 2
                    ),
                    "transfer_stations_eur": round(xfer_stn * grid_ann_ratio, 2),
                    "pumps_eur": round(
                        optimizer.pump_cost_cumulative * grid_ann_ratio, 2
                    ),
                    "connection_pipelines_eur": round(
                        pipeline_conn * grid_ann_ratio, 2
                    ),
                },
            },
            "edges": all_edges,
        }

    subgraphs = []
    for result in optimization_results:
        subgraph_id = result.subgraph_id
        is_connected = result.is_connected

        subgraph_demand = _get_val(
            attrs.loc[subgraph_id, "Annual Heat Demand [MWh/a]"]
        )
        subgraph_buildings = int(_get_val(attrs.loc[subgraph_id, "Total building count"]))
        subgraph_peak_load_mw = _get_val(attrs.loc[subgraph_id, "Peak Load [MW]"])
        subgraph_network_length = _get_val(
            attrs.loc[subgraph_id, "Total network length [m]"]
        )
        subgraph_average_lhd = _get_val(
            attrs.loc[subgraph_id, "Average Linear Heat Density [MWh/m/a]"]
        )

        building_demands = _get_list(
            attrs.loc[subgraph_id], "Building Annual Demands [MWh/a]"
        )
        building_peak_loads_kw = [round(demand * 1000 / flh, 4) for demand in building_demands]
        subgraph_edges = _extract_edges(optimizer.subgraph_dict[subgraph_id])

        subgraph_entry: dict[str, object] = {
            "subgraph_id": int(subgraph_id),
            "is_connected": is_connected,
            "annual_heat_demand_mwh": round(subgraph_demand, 4),
            "peak_load_mw": round(subgraph_peak_load_mw, 4),
            "buildings": subgraph_buildings,
            "share_of_combined_demand_pct": round(
                subgraph_demand / connected_demand * 100, 2
            )
            if connected_demand > 0 and is_connected
            else 0,
            "total_network_length_m": round(subgraph_network_length, 2),
            "average_linear_heat_density_mwh_per_m_a": round(
                subgraph_average_lhd, 4
            ),
            "building_peak_loads_kw": building_peak_loads_kw,
            "building_annual_demands_mwh": [round(demand, 4) for demand in building_demands],
            "edges": subgraph_edges,
        }

        if is_connected:
            stored_solution = optimizer.opt_results_central[subgraph_id]
            result_df = _require_result_frame(stored_solution)
            central_portfolio = portfolio_from_stored_result(stored_solution)
            subgraph_entry["central_cumulative_supply"] = {
                "cumulative_demand_mwh": round(
                    float(result_df["demand_heat"].sum() * dt / 1000), 4
                ),
                "supply": central_portfolio["supply"],
                "storage": central_portfolio["storage"],
                "total_heat_production_mwh": central_portfolio[
                    "total_heat_production_mwh"
                ],
                "cost_annualized_eur": round(result.central_cost, 2),
            }

        cluster_details = optimizer.cluster_details.get(subgraph_id, {})
        if cluster_details:
            clusters_list = []
            cluster_portfolios: list[tuple[Mapping[str, object], float]] = []

            for cluster_id, cluster_info in sorted(cluster_details.items()):
                cluster_portfolio = cluster_info.get("portfolio")
                centroid_demand = float(cluster_info.get("centroid_demand", 0))
                total_cluster_demand = float(cluster_info.get("total_demand", 0))
                scaling_factor = (
                    total_cluster_demand / centroid_demand
                    if centroid_demand > 0
                    else 1.0
                )

                cluster_entry = {
                    "cluster_id": int(cluster_id),
                    "n_buildings": int(cluster_info.get("n_buildings", 0)),
                    "centroid_demand_mwh": round(centroid_demand, 4),
                    "total_demand_mwh": round(total_cluster_demand, 4),
                    "scaling_factor": round(scaling_factor, 4),
                }
                if cluster_portfolio:
                    cluster_entry["supply"] = cluster_portfolio["supply"]
                    cluster_entry["storage"] = cluster_portfolio["storage"]
                    cluster_entry["unscaled_annualized_cost_eur"] = round(
                        float(cluster_info.get("cost", 0)), 2
                    )
                    cluster_entry["scaled_annualized_cost_eur"] = round(
                        float(
                            cluster_info.get(
                                "scaled_cost", cluster_info.get("cost", 0)
                            )
                        ),
                        2,
                    )
                    cluster_entry["cost_breakdown"] = build_cost_breakdown(
                        cluster_portfolio,
                        ctx,
                        decentral_bool=True,
                    )
                    cluster_portfolios.append((cluster_portfolio, scaling_factor))

                clusters_list.append(cluster_entry)

            # Keep the historical aggregate energy shape while using the same
            # portfolio presentation rules for every reporting path.  Calculate
            # the total from unrounded values to preserve the legacy result.
            aggregated_supply = aggregate_supply_energy(cluster_portfolios)
            aggregated_total_energy = sum(
                portfolio_energy_mwh(technology, technology_result) * scaling_factor
                for cluster_portfolio, scaling_factor in cluster_portfolios
                for technology, technology_result in cluster_portfolio.get(
                    "supply", {}
                ).items()
            )

            decentral_key = "decentral_alternative" if is_connected else "decentral_supply"
            subgraph_entry[decentral_key] = {
                "total_annualized_cost_eur": round(result.decentral_cost, 2),
                "clusters": clusters_list,
                "aggregated_supply": aggregated_supply,
                "aggregated_total_energy_mwh": round(aggregated_total_energy, 4),
            }

        subgraphs.append(subgraph_entry)

    return {
        "summary": summary,
        "combined_graph": combined_graph,
        "subgraphs": subgraphs,
    }


__all__ = ["assemble_full_results"]
