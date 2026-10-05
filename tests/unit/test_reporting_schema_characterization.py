from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from dh_compass.optimization.model_inputs import (
    ContextTechnologyPortfolio,
    ResourceLimits,
    TechnologyPortfolio,
)
from dh_compass.optimization.result_extraction import ModelSolution
from dh_compass.reporting.charts import generate_all_charts
from dh_compass.reporting.json_export import save_full_results_json
from dh_compass.reporting.result_schema import assemble_full_results
from dh_compass.reporting.viewer_export import (
    _build_potential_limits,
    export_viewer_data,
    save_viewer_data,
)


def _fake_optimizer():
    graph = nx.MultiGraph()
    graph.add_node(1, x=7.0, y=51.0)
    graph.add_node(2, x=7.001, y=51.001)
    graph.add_edge(
        1,
        2,
        key=0,
        length=100.0,
        heat_demand=12.5,
        peak_load=4.0,
        linear_heat_density=0.125,
        building_count_edge=2,
    )
    attributes = pd.DataFrame(
        [
            {
                "Subgraph ID": 1,
                "Annual Heat Demand [MWh/a]": 12.5,
                "Total building count": 2,
                "Peak Load [MW]": 0.004,
                "Total network length [m]": 100.0,
                "Average Linear Heat Density [MWh/m/a]": 0.125,
                "Building Annual Demands [MWh/a]": [5.0, 7.5],
                "Total distribution pipe cost [€]": 1000.0,
                "Total building connection cost [€]": 500.0,
                "Total transfer station cost [€]": 200.0,
            }
        ]
    ).set_index("Subgraph ID")

    result_columns = [
        "hp_h",
        "hb_h",
        "chp_h",
        "eb_h",
        "ieh_h",
        "bm_hb_h",
        "bm_chp_h",
        "wte_h",
        "geo_h",
        "hp_river_h",
        "hp_wwtp_h",
        "demand_heat",
        "z_D",
        "y_S_PV",
        "y_S_CHP",
        "y_S_BM_CHP",
        "hb_f",
        "chp_f",
        "bm_hb_f",
        "bm_chp_f",
        "hp_e",
        "hp_river_e",
        "hp_wwtp_e",
        "eb_e",
    ]
    result_df = pd.DataFrame([[0.0] * len(result_columns)], columns=result_columns)
    central_market = SimpleNamespace(
        dt=1.0,
        fuel_price=[],
        elec_price=[],
        fuel_price_biomass=[],
        price_sell_pv=[],
        price_sell_chp=[],
    )
    context = SimpleNamespace(
        economic=SimpleNamespace(
            interest_rate=0.05,
            investment_duration=20,
            inv_cost={},
            fixed_cost={},
            var_om_cost={},
        ),
        market=SimpleNamespace(
            central=central_market,
            decentral=central_market,
            for_model=lambda _decentral: central_market,
        ),
        technologies=SimpleNamespace(
            central=SimpleNamespace(),
            for_model=lambda _decentral: SimpleNamespace(),
        ),
        resources=ResourceLimits(),
        network=SimpleNamespace(
            residual_value_factor_pipeline=0.1,
            pipeline_cost_per_m=10.0,
            infrastructure_cost_factor=1.0,
        ),
    )
    return SimpleNamespace(
        ctx=context,
        subgraph_attributes_df=attributes,
        connected_subgraphs=[1],
        subgraph_dict={1: graph},
        opt_results_central={1: (2000.0, ModelSolution(result_df=result_df))},
        cluster_details={},
        iteration_history=[],
        grid_cost_cumulative=1000.0,
        pump_cost_cumulative=20.0,
        total_cost_central_cumulative=2000.0,
        connecting_edges_df=pd.DataFrame(
            {"path_length": [20.0], "path": [[1, 2]]}
        ),
    )


def _result():
    return SimpleNamespace(
        subgraph_id=1,
        is_connected=True,
        central_cost=2000.0,
        decentral_cost=2500.0,
        grid_cost=1000.0,
        connection_length=20.0,
    )


def test_full_results_json_schema_and_stable_values(assert_json_characterization):
    actual = assemble_full_results(_fake_optimizer(), [_result()], flh=3000)
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "full_results.json"
    expected = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert_json_characterization(actual, expected)


def test_full_results_rejects_solution_without_time_series():
    optimizer = _fake_optimizer()
    optimizer.opt_results_central[1] = (2000.0, ModelSolution())

    with pytest.raises(ValueError, match="without result_df"):
        assemble_full_results(optimizer, [_result()], flh=3000)


def test_json_persistence_converts_native_values(tmp_path):
    output_path = tmp_path / "full_results.json"

    save_full_results_json({"values": np.array([np.int64(2), np.nan])}, output_path)

    assert json.loads(output_path.read_text(encoding="utf-8")) == {"values": [2, None]}


def test_viewer_export_accepts_domain_results_and_serializes(tmp_path):
    optimizer = _fake_optimizer()
    street_network = optimizer.subgraph_dict[1]
    config = SimpleNamespace(
        scenario=SimpleNamespace(case="test"),
        network=SimpleNamespace(flh=3000, linear_heat_density_threshold=0.1),
    )

    viewer_data = export_viewer_data(
        optimizer,
        [_result()],
        street_network,
        street_network,
        config,
    )
    output_path = tmp_path / "viewer_data.json"
    save_viewer_data(
        viewer_data,
        output_path,
        template_path=tmp_path / "missing-viewer-template.html",
    )

    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["subgraphs"]["1"]["is_connected"] is True
    assert persisted["subgraphs"]["1"]["supply"] == {}


def test_viewer_reports_biomass_when_only_chp_is_enabled():
    disabled = {0: {"on_off": 0}}
    technologies = TechnologyPortfolio(
        battery_storage=disabled,
        chp=disabled,
        boiler=disabled,
        heat_pump=disabled,
        electrode_boiler=disabled,
        heat_storage=disabled,
        industrial_eh=disabled,
        biomass_boiler={0: {"on_off": 0, "efficiency": 0.9}},
        biomass_chp={
            0: {
                "on_off": 1,
                "efficiency_electric": 0.14,
                "power_to_heat_ratio": 5.0,
            }
        },
        waste_to_energy=disabled,
        geothermal=disabled,
        river_heat_pump=disabled,
        wwtp_heat_pump=disabled,
    )
    context = SimpleNamespace(
        resources=ResourceLimits(biomass_energy_limit_mwh=125.0),
        technologies=ContextTechnologyPortfolio(
            central=technologies,
            decentral=technologies,
        ),
    )

    limits = _build_potential_limits(context)

    assert limits["biomass"]["limit"] == 125.0
    assert limits["biomass"]["shared_techs"] == ["biomass_boiler", "biomass_chp"]


def test_charts_consume_stable_full_results_schema(tmp_path):
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "full_results.json"
    generate_all_charts(json.loads(fixture_path.read_text(encoding="utf-8")), tmp_path)

    assert (tmp_path / "chart_cost_structure.png").is_file()
    assert (tmp_path / "chart_cost_detailed.png").is_file()
    assert (tmp_path / "chart_cost_pie.png").is_file()
