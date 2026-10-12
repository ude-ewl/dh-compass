"""Solver-independent protection for DH-only loss accounting."""

from types import SimpleNamespace

import pandas as pd
import pytest

from dh_compass.config import ConfigurationError, load_config
from dh_compass.network.losses import network_input_heat
from dh_compass.optimization.candidate_evaluator import CandidateEvaluator
from dh_compass.optimization.connection_evaluator import ConnectionEvaluator, GridCostResult
from dh_compass.optimization.model_inputs import ContextDemandData, ModelOptions, build_model_inputs
from dh_compass.optimization.model_runner import ModelRunner
from dh_compass.optimization.run_state import OptimizationRunState
from dh_compass.reporting.heat_balance import heat_balance_metrics


def _context(loss_fraction):
    market = SimpleNamespace(
        dt=0.5, fuel_price=[0.0, 0.0], elec_price=[0.0, 0.0],
        price_sell_pv=[0.0, 0.0], price_sell_chp=[0.0, 0.0],
    )
    return SimpleNamespace(
        economic=None,
        resources=None,
        options=ModelOptions(),
        network=SimpleNamespace(
            heat_loss_fraction=loss_fraction,
            infrastructure_cost_factor=1.0,
            residual_value_factor_pipeline=0.0,
        ),
        market=SimpleNamespace(for_model=lambda _: market),
        technologies=SimpleNamespace(for_model=lambda _: None),
        demand=ContextDemandData(*([[0.0, 0.0]] * 7)),
        clustering=SimpleNamespace(n_clusters=1, random_state=42),
        runtime_services=SimpleNamespace(pump_cost_func=lambda peak: peak * 2),
    )


@pytest.mark.parametrize("fraction", [0.0, 0.1, 0.125, 0.15])
@pytest.mark.parametrize("as_series", [False, True])
def test_conversion_preserves_delivered_profile(fraction, as_series):
    demand = pd.Series([0.0, 100.0], index=[7, 9]) if as_series else [0.0, 100.0]
    original = demand.copy()
    converted = network_input_heat(demand, fraction)
    assert list(converted) == pytest.approx([0.0, 100 / (1 - fraction)])
    if as_series:
        pd.testing.assert_series_equal(demand, original)
        assert converted.index.equals(demand.index)
    else:
        assert demand == original
    if fraction == 0:
        assert converted is demand


@pytest.mark.parametrize("fraction", [-0.01, 1.0, 1.01, float("nan"), float("inf"), True])
def test_runtime_rejects_invalid_loss_fraction(fraction):
    with pytest.raises(ValueError, match="heat_loss_fraction"):
        network_input_heat([100.0], fraction)


@pytest.mark.parametrize("value", ["-0.01", "1", "1.01", "nan", "inf", "true", '"0.1"'])
def test_configuration_rejects_invalid_loss_fraction(project_root, tmp_path, value):
    path = tmp_path / "losses.toml"
    path.write_text(f"[network]\nheat_loss_fraction = {value}\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="heat_loss_fraction"):
        load_config(config_path=path, project_root=project_root)


@pytest.mark.parametrize("fraction", [0.0, 0.1, 0.125, 0.15])
def test_configuration_inherits_and_overrides_loss_fraction(project_root, tmp_path, fraction):
    path = tmp_path / "losses.toml"
    path.write_text(f"[network]\nheat_loss_fraction = {fraction}\n", encoding="utf-8")
    assert load_config(config_path=path, project_root=project_root).network.heat_loss_fraction == fraction


def test_adapter_only_converts_central_heat_demand():
    context = _context(0.125)
    delivered = pd.Series([100.0, 200.0])
    central = build_model_inputs(context, delivered, decentral=False)
    decentral = build_model_inputs(context, delivered, decentral=True)
    assert central.demand.demand_heat.tolist() == pytest.approx([100 / 0.875, 200 / 0.875])
    assert decentral.demand.demand_heat is delivered
    assert central.demand.solar_heat is context.demand.solar_heat
    assert central.resources is context.resources
    assert delivered.tolist() == [100.0, 200.0]


def _runner(context, captured):
    def build(inputs):
        captured.append(inputs)
        return SimpleNamespace(
            inputs=inputs, solver_name="mock", optimize=lambda: None,
            objective_value=float(sum(inputs.demand.demand_heat)),
        )

    def gather(model, _pv, _electric, delivered, *_args):
        # Include excess production to prove losses are not inferred from it.
        return pd.DataFrame({"demand_heat": list(delivered), "hb_h": [1000.0, 1000.0]}), {}

    return ModelRunner(context, model_builder=build, results_gatherer=gather, reuse_models=False)


def test_candidate_accumulation_does_not_compound_losses():
    context = _context(0.125)
    captured = []
    attributes = pd.DataFrame([
        {"Subgraph ID": 1, "Load Profile": {"load": pd.Series([1.0, 2.0])},
         "Building Annual Demands [MWh/a]": [1.0]},
        {"Subgraph ID": 2, "Load Profile": {"load": pd.Series([3.0, 4.0])},
         "Building Annual Demands [MWh/a]": [2.0]},
    ])
    evaluator = CandidateEvaluator(
        context, attributes, model_runner=_runner(context, captured),
        cluster_solver=SimpleNamespace(solve=lambda *_args, **_kwargs: (10000.0, {})),
        connection_evaluator=SimpleNamespace(
            find_shortest_connection=lambda *_args: None,
            calculate_grid_cost=lambda *_args, **_kwargs: GridCostResult(0.0, 0.0, 0.0, None),
        ),
        annuity_factor_value=1.0,
    )
    state = OptimizationRunState()
    evaluator.evaluate(1, state, is_first=True)
    evaluation = evaluator.evaluate(2, state, is_first=False)
    assert state.connected_subgraphs == [1, 2]
    assert state.demand_heat_cumulative.tolist() == [4.0, 6.0]
    assert captured[0].demand.demand_heat.tolist() == pytest.approx([1 / 0.875, 2 / 0.875])
    assert captured[1].demand.demand_heat.tolist() == pytest.approx([4 / 0.875, 6 / 0.875])
    frame = evaluation.central_run.solution.result_df
    assert frame["demand_heat"].tolist() == [4.0, 6.0]
    assert frame["network_input_heat"].tolist() == pytest.approx([4 / 0.875, 6 / 0.875])
    assert heat_balance_metrics(frame, 0.5, 0.125) == {
        "heat_loss_fraction": 0.125,
        "annual_network_input_heat_mwh": 0.0057,
        "annual_distribution_heat_loss_mwh": 0.0007,
        "network_input_peak_load_kw": 6.8571,
    }


@pytest.mark.parametrize("fraction", [0.0, 0.1, 0.125, 0.15])
def test_source_side_pump_uses_network_input_peak(fraction):
    attributes = pd.DataFrame([{
        "Subgraph ID": 1, "Total distribution pipe cost [€]": 10.0,
        "Total building connection cost [€]": 20.0, "Total transfer station cost [€]": 30.0,
    }])
    evaluator = ConnectionEvaluator(None, {}, attributes, _context(fraction))
    delivered = pd.Series([100.0, 200.0])
    result = evaluator.calculate_grid_cost(1, delivered, OptimizationRunState(), is_first=True)
    assert result.pump_cost == pytest.approx(400 / (1 - fraction))
    assert result.grid_cost == pytest.approx(60 + result.pump_cost)
    assert delivered.tolist() == [100.0, 200.0]


def test_loss_metrics_integrate_timestep_and_ignore_storage_dumped_heat():
    frame = pd.DataFrame({
        "demand_heat": [1000.0, 2000.0], "network_input_heat": [1250.0, 2500.0],
        "hs_C": [50.0, 100.0], "heat_dumped": [200.0, 300.0], "hb_h": [9000.0, 9000.0],
    })
    metrics = heat_balance_metrics(frame, 0.25, 0.2)
    assert metrics["annual_network_input_heat_mwh"] == 0.9375
    assert metrics["annual_distribution_heat_loss_mwh"] == 0.1875
    assert metrics["network_input_peak_load_kw"] == 2500.0
