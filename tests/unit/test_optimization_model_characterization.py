from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pandas as pd
import pytest
from mip import CBC
from mip import Model as MipModel

import dh_compass.optimization.model as model_module
from dh_compass.optimization.model import annuity_factor, npv_factor
from dh_compass.optimization.model_inputs import (
    DemandTimeSeries,
    EconomicInputs,
    MarketTimeSeries,
    ModelInputs,
    ModelOptions,
    ResourceLimits,
    TechnologyPortfolio,
)


def _technology(*, on_off: int = 0, **overrides):
    values = {
        "efficiency": 1.0,
        "on_off": on_off,
        "power_to_heat_ratio": 1.0,
        "efficiency_electric": 0.5,
        "lifetime": 20,
        "reinvest_factor": 0.0,
        "residual_value_factor": 0.0,
        "energy_to_power": 2.0,
        "efficiency_charge": 1.0,
        "efficiency_discharge": 1.0,
    }
    values.update(overrides)
    return {0: values}


def _constant_cost(value: float):
    return lambda _capacity, value=value: value


def _base_model_inputs(**overrides):
    n_steps = 3
    inputs = {
        "dt": 1.0,
        "fuel_price": [0.0] * n_steps,
        "price_sell_pv": [0.0] * n_steps,
        "price_sell_chp": [0.0] * n_steps,
        "elec_price": [0.0] * n_steps,
        "demand_electric": pd.Series([0.0] * n_steps),
        "demand_heat": pd.Series([10.0, 20.0, 15.0]),
        "pv_infeed": pd.Series([0.0] * n_steps),
        "cop": [3.0] * n_steps,
        "timestamps": pd.Series(range(n_steps)),
        "battery_storage": _technology(),
        "chp": _technology(power_to_heat_ratio=1.5),
        "boiler": _technology(efficiency=0.9),
        "heat_pump": _technology(),
        "electrode_boiler": _technology(efficiency=0.99),
        "solar_heat": [0.0] * n_steps,
        "heat_storage": _technology(),
        "industrial_eh": _technology(),
        "industrial_eh_energy_limit_mwh": 1.0,
        "biomass_boiler": _technology(efficiency=0.9),
        "biomass_chp": _technology(
            power_to_heat_ratio=1.5, efficiency_electric=0.5
        ),
        "biomass_energy_limit_mwh": 1.0,
        "fuel_price_biomass": [0.0] * n_steps,
        "waste_to_energy": _technology(),
        "wte_energy_limit_mwh": 1.0,
        "geothermal": _technology(),
        "geothermal_energy_limit_mwh": 1.0,
        "river_heat_pump": _technology(),
        "river_hp_capacity_limit_kw": 50.0,
        "cop_river_hp": [3.0] * n_steps,
        "wwtp_heat_pump": _technology(),
        "wwtp_hp_capacity_limit_kw": 50.0,
        "cop_wwtp_hp": [3.0] * n_steps,
        "inv_cost": {
            "chp": _constant_cost(0.0),
            "hb": {"central": _constant_cost(0.0), "decentral": _constant_cost(0.0)},
            "hs": {"central": _constant_cost(0.0), "decentral": _constant_cost(0.0)},
            "bs": _constant_cost(0.0),
            "hp": {"central": _constant_cost(0.0), "decentral": _constant_cost(0.0)},
            "eb": _constant_cost(0.0),
            "ieh": _constant_cost(0.0),
            "bm_hb": _constant_cost(0.0),
            "bm_chp": _constant_cost(0.0),
            "wte": _constant_cost(0.0),
            "geo": _constant_cost(0.0),
            "hp_river": _constant_cost(0.0),
            "hp_wwtp": _constant_cost(0.0),
        },
        "fixed_cost": {
            "chp": _constant_cost(0.0),
            "hb": {"central": _constant_cost(0.0), "decentral": _constant_cost(0.0)},
            "hs": _constant_cost(0.0),
            "bs": _constant_cost(0.0),
            "hp": {"central": _constant_cost(0.0), "decentral": _constant_cost(0.0)},
            "eb": _constant_cost(0.0),
            "ieh": _constant_cost(0.0),
            "bm_hb": _constant_cost(0.0),
            "bm_chp": _constant_cost(0.0),
            "wte": _constant_cost(0.0),
            "geo": _constant_cost(0.0),
            "hp_river": _constant_cost(0.0),
            "hp_wwtp": _constant_cost(0.0),
        },
        "var_om_cost": {
            "chp": _constant_cost(0.0),
            "hb": {"central": _constant_cost(0.0)},
            "ieh": _constant_cost(0.0),
            "bm_hb": _constant_cost(0.0),
            "bm_chp": _constant_cost(0.0),
            "wte": _constant_cost(0.0),
            "geo": _constant_cost(0.0),
        },
        "interest_rate": 0.05,
        "investment_duration": 20,
        "electricity_price_annual_change": 1.0,
        "gas_price_annual_change": 1.0,
        "pv_rem_annual_change": 1.0,
        "chp_rem_annual_change": 1.0,
        "ref_binary": 0,
        "decentral_bool": 0,
        "decentral_heat_storage_intercept": 23.345,
        "decentral_heat_storage_slope": 0.617,
    }
    inputs.update(overrides)
    return inputs


def _typed_inputs(values) -> ModelInputs:
    """Build the public typed boundary directly for model characterization."""

    return ModelInputs(
        economic=EconomicInputs(
            interest_rate=values["interest_rate"],
            investment_duration=values["investment_duration"],
            electricity_price_annual_change=values["electricity_price_annual_change"],
            gas_price_annual_change=values["gas_price_annual_change"],
            pv_rem_annual_change=values["pv_rem_annual_change"],
            chp_rem_annual_change=values["chp_rem_annual_change"],
            inv_cost=values["inv_cost"],
            fixed_cost=values["fixed_cost"],
            var_om_cost=values["var_om_cost"],
        ),
        market=MarketTimeSeries(
            dt=values["dt"],
            timestamps=values["timestamps"],
            fuel_price=values["fuel_price"],
            elec_price=values["elec_price"],
            price_sell_pv=values["price_sell_pv"],
            price_sell_chp=values["price_sell_chp"],
            fuel_price_biomass=values["fuel_price_biomass"],
        ),
        demand=DemandTimeSeries(
            demand_electric=values["demand_electric"],
            demand_heat=values["demand_heat"],
            pv_infeed=values["pv_infeed"],
            cop=values["cop"],
            solar_heat=values["solar_heat"],
            cop_river_hp=values["cop_river_hp"],
            cop_wwtp_hp=values["cop_wwtp_hp"],
        ),
        technologies=TechnologyPortfolio(
            battery_storage=values["battery_storage"],
            chp=values["chp"],
            boiler=values["boiler"],
            heat_pump=values["heat_pump"],
            electrode_boiler=values["electrode_boiler"],
            heat_storage=values["heat_storage"],
            industrial_eh=values["industrial_eh"],
            biomass_boiler=values["biomass_boiler"],
            biomass_chp=values["biomass_chp"],
            waste_to_energy=values["waste_to_energy"],
            geothermal=values["geothermal"],
            river_heat_pump=values["river_heat_pump"],
            wwtp_heat_pump=values["wwtp_heat_pump"],
        ),
        resources=ResourceLimits(
            industrial_eh_energy_limit_mwh=values["industrial_eh_energy_limit_mwh"],
            biomass_energy_limit_mwh=values["biomass_energy_limit_mwh"],
            wte_energy_limit_mwh=values["wte_energy_limit_mwh"],
            geothermal_energy_limit_mwh=values["geothermal_energy_limit_mwh"],
            river_hp_capacity_limit_kw=values["river_hp_capacity_limit_kw"],
            wwtp_hp_capacity_limit_kw=values["wwtp_hp_capacity_limit_kw"],
        ),
        options=ModelOptions(
            ref_binary=values["ref_binary"],
            decentral_bool=values["decentral_bool"],
            decentral_heat_storage_intercept=values[
                "decentral_heat_storage_intercept"
            ],
            decentral_heat_storage_slope=values["decentral_heat_storage_slope"],
        ),
    )


def _build_model(monkeypatch, **overrides):
    def cbc_model(**_kwargs):
        model = MipModel(solver_name=CBC)
        model.verbose = 0
        return model

    monkeypatch.setattr(model_module, "Model", cbc_model)
    return model_module.generate_deterministic_model_mip(
        _typed_inputs(_base_model_inputs(**overrides))
    )


def _optimize(model):
    model.optimize()
    assert str(model.status).endswith("OPTIMAL")
    return model


def _values(model, name: str) -> list[float]:
    return [variable.x for variable in model.vars if variable.name == name]


@pytest.mark.parametrize(
    ("input_name", "capacity_name", "heat_flow_name"),
    [
        ("boiler", "power_heat_boiler", "hb_h"),
        ("chp", "power_chp", "chp_h"),
        ("heat_pump", "power_heat_heat_pump", "hp_h"),
        ("electrode_boiler", "power_eb", "eb_h"),
        ("industrial_eh", "power_ieh", "ieh_h"),
        ("biomass_boiler", "power_bm_hb", "bm_hb_h"),
        ("biomass_chp", "power_bm_chp", "bm_chp_h"),
        ("waste_to_energy", "power_wte", "wte_h"),
        ("geothermal", "power_geo", "geo_h"),
        ("river_heat_pump", "power_hp_river", "hp_river_h"),
        ("wwtp_heat_pump", "power_hp_wwtp", "hp_wwtp_h"),
    ],
)
def test_enabled_heat_technology_supplies_synthetic_demand(
    monkeypatch, input_name, capacity_name, heat_flow_name
):
    inputs = _base_model_inputs()
    inputs[input_name] = _technology(on_off=1)

    model = _optimize(_build_model(monkeypatch, **inputs))

    assert model.vars[capacity_name].x > 0
    assert sum(_values(model, heat_flow_name)) == pytest.approx(
        sum(inputs["demand_heat"])
    )


@pytest.mark.parametrize("backend", [CBC, "HiGHS"])
def test_reused_lp_matches_fresh_build_after_demand_and_cost_changes(monkeypatch, backend):
    from dh_compass.optimization.model import update_model_demand

    # A nonzero solar profile catches incorrect RHS signs. Capacity-dependent
    # investment costs must be reevaluated at the new peak, not carried over.
    values = _base_model_inputs(
        boiler=_technology(on_off=1, efficiency=0.9),
        heat_pump=_technology(on_off=1),
        fuel_price=[0.1] * 3, elec_price=[0.2] * 3,
        solar_heat=[2.0, 4.0, 1.0],
    )
    values["inv_cost"]["hb"]["central"] = lambda peak: 200.0 / (1 + peak)
    values["inv_cost"]["hp"]["central"] = lambda peak: 300.0 / (1 + peak)
    inputs = _typed_inputs(values)
    def factory():
        model = MipModel(solver_name=backend)
        if backend == "HiGHS":
            from dh_compass.optimization.highs_backend import HeatGridHighsSolver

            model.solver = HeatGridHighsSolver(model, "", model.sense)
            model.threads = 1
        return model

    monkeypatch.setattr(model_module, "create_solver_model", factory)
    reused = model_module.generate_deterministic_model_mip(inputs)
    reused.verbose = 0
    if backend == "HiGHS":
        reused.solver.normalize(float(max(inputs.demand.demand_heat)))
    _optimize(reused)
    changed = replace(inputs, demand=replace(inputs.demand, demand_heat=pd.Series([50.0, 80.0, 35.0])))
    assert update_model_demand(reused, changed)
    if backend == "HiGHS":
        reused.solver.normalize(float(max(changed.demand.demand_heat)))
    _optimize(reused)
    fresh = model_module.generate_deterministic_model_mip(changed)
    fresh.verbose = 0
    _optimize(fresh)
    assert reused.objective_value == pytest.approx(fresh.objective_value, rel=1e-8)
    assert _values(reused, "hb_h") == pytest.approx(_values(fresh, "hb_h"))
    assert _values(reused, "hp_h") == pytest.approx(_values(fresh, "hp_h"))
    assert reused.num_rows == fresh.num_rows
    assert reused.num_cols == fresh.num_cols


def test_lp_reuse_rejects_changed_context_and_invalid_demand(monkeypatch):
    from dh_compass.optimization.model import update_model_demand

    inputs = _typed_inputs(_base_model_inputs(boiler=_technology(on_off=1)))
    monkeypatch.setattr(model_module, "create_solver_model", lambda: MipModel(solver_name=CBC))
    model = model_module.generate_deterministic_model_mip(inputs)
    assert not update_model_demand(model, replace(inputs, options=replace(inputs.options, decentral_bool=1)))
    assert not update_model_demand(model, replace(inputs, resources=ResourceLimits(biomass_energy_limit_mwh=10)))
    assert not update_model_demand(model, replace(inputs, demand=replace(inputs.demand, solar_heat=[0, 1, 0])))
    with pytest.raises(ValueError, match="same length"):
        update_model_demand(model, replace(inputs, demand=replace(inputs.demand, demand_heat=[1])))


@pytest.mark.parametrize("backend", [CBC, "HiGHS"])
def test_model_runner_reuses_models_and_keeps_modes_separate(monkeypatch, backend):
    from types import SimpleNamespace

    from dh_compass.optimization.model_inputs import (
        ContextDemandData,
        ContextMarketData,
        ContextTechnologyPortfolio,
    )
    from dh_compass.optimization.model_runner import ModelRunner

    inputs = _typed_inputs(_base_model_inputs(
        boiler=_technology(on_off=1), fuel_price=[0.1] * 3,
        decentral_heat_storage_intercept=0, decentral_heat_storage_slope=0,
    ))
    context = SimpleNamespace(
        economic=inputs.economic, resources=inputs.resources, options=inputs.options,
        market=ContextMarketData(inputs.market, inputs.market),
        technologies=ContextTechnologyPortfolio(inputs.technologies, inputs.technologies),
        demand=ContextDemandData(
            inputs.demand.demand_electric, inputs.demand.pv_infeed,
            inputs.demand.solar_heat, inputs.demand.cop, inputs.demand.cop,
            inputs.demand.cop_river_hp, inputs.demand.cop_wwtp_hp,
        ),
    )
    models = []

    def build(new_inputs):
        model = model_module.generate_deterministic_model_mip(new_inputs)
        model.verbose = 0
        models.append(model)
        return model

    def factory():
        model = MipModel(solver_name=backend)
        if backend == "HiGHS":
            from dh_compass.optimization.highs_backend import HeatGridHighsSolver

            model.solver = HeatGridHighsSolver(model, "", model.sense)
            model.threads = 1
        return model

    monkeypatch.setattr(model_module, "create_solver_model", factory)
    runner = ModelRunner(context, model_builder=build)
    first = runner.run(pd.Series([10, 20, 15]), use_gathered_results=False)
    changed = runner.run(pd.Series([20, 40, 30]), use_gathered_results=False)
    decentralized = runner.run(pd.Series([10, 20, 15]), decentral=True, use_gathered_results=True)
    assert len(models) == 2
    assert changed.objective_value == pytest.approx(2 * first.objective_value)
    # Returned solutions are values; subsequent solves must not mutate them.
    assert first.solution.supply["boiler"].capacity_kw == pytest.approx(20)
    assert decentralized.solution.supply["boiler"].capacity_kw == pytest.approx(20)
    assert decentralized.objective_value == pytest.approx(4.5)
    if backend == "HiGHS":
        from concurrent.futures import ThreadPoolExecutor

        from mip import LP_Method

        assert models[0].lp_method == LP_Method.BARRIER
        assert models[0].solver.normalization_scale == 1
        assert models[1].solver.normalization_scale == 20

        def run_size(size):
            return runner.run(
                pd.Series([10, 20, 15]) * size, solver_threads=2,
                decentral=True, use_gathered_results=False,
            )

        with ThreadPoolExecutor(max_workers=4) as executor:
            runs = list(executor.map(run_size, [1, 2, 3, 4]))
        assert [run.objective_value for run in runs] == pytest.approx([4.5, 9, 13.5, 18])
        assert all(model.threads == 1 for model in models)
        assert len(runner._models[False]) == 1


def test_model_builder_requires_typed_inputs():
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        model_module.generate_deterministic_model_mip(**_base_model_inputs())


def test_typed_model_inputs_build_the_same_solver_model(monkeypatch):
    model = _optimize(
        _build_model(
            monkeypatch,
            boiler=_technology(on_off=1, efficiency=0.9),
        )
    )

    assert _values(model, "hb_h") == pytest.approx([10.0, 20.0, 15.0])
    assert model.vars["power_heat_boiler"].x == pytest.approx(20.0)


def test_highs_fallback_matches_characterized_heat_model(monkeypatch):
    from mip import GRB, HIGHS, InterfacingError

    values = _base_model_inputs(boiler=_technology(on_off=1, efficiency=0.9))
    cbc = _optimize(_build_model(monkeypatch, **values))

    def factory(*, solver_name):
        if solver_name == GRB:
            raise InterfacingError("Simulated unavailable Gurobi license")
        model = MipModel(solver_name=solver_name)
        model.verbose = 0
        return model

    monkeypatch.setattr(model_module, "_selected_backend", None)
    monkeypatch.setattr(model_module, "Model", factory)
    highs = _optimize(model_module.generate_deterministic_model_mip(_typed_inputs(values)))
    assert highs.solver_name == HIGHS
    assert highs.objective_value == pytest.approx(cbc.objective_value)
    assert _values(highs, "hb_h") == pytest.approx([10.0, 20.0, 15.0])
    assert highs.vars["power_heat_boiler"].x == pytest.approx(20.0)
    assert len(highs.vars) == len(cbc.vars)
    assert len(highs.constrs) == len(cbc.constrs)


def test_model_inputs_reject_mismatched_time_series():
    inputs = _base_model_inputs(elec_price=[0.0, 0.0])

    with pytest.raises(ValueError, match="same length"):
        _typed_inputs(inputs).validate()


def test_battery_shifts_pv_to_later_electric_demand(monkeypatch):
    model = _optimize(
        _build_model(
            monkeypatch,
            demand_heat=pd.Series([0.0, 0.0, 0.0]),
            demand_electric=pd.Series([0.0, 10.0, 0.0]),
            pv_infeed=pd.Series([10.0, 0.0, 0.0]),
            elec_price=[0.0, 1.0, 0.0],
            battery_storage=_technology(on_off=1, energy_to_power=1.0),
        )
    )

    assert sum(_values(model, "s_C")) == pytest.approx(10.0)
    assert sum(_values(model, "s_D")) == pytest.approx(10.0)
    assert model.vars["capacity_bs"].x == pytest.approx(10.0)


def test_heat_storage_shifts_solar_heat_to_later_demand(monkeypatch):
    model = _optimize(
        _build_model(
            monkeypatch,
            demand_heat=pd.Series([0.0, 10.0, 0.0]),
            solar_heat=[10.0, 0.0, 0.0],
            boiler=_technology(on_off=1, efficiency=0.9),
            heat_storage=_technology(on_off=1, energy_to_power=1.0),
        )
    )

    assert sum(_values(model, "hs_C")) == pytest.approx(10.0)
    assert sum(_values(model, "hs_D")) == pytest.approx(10.0)
    assert model.vars["capacity_hs"].x == pytest.approx(10.0)


def test_zero_demand_does_not_create_capacity(monkeypatch):
    model = _build_model(
        monkeypatch,
        demand_heat=pd.Series([0.0, 0.0, 0.0]),
        boiler=_technology(on_off=1),
    )
    _optimize(model)

    assert model.vars["power_heat_boiler"].x == pytest.approx(0.0)
    assert sum(v.x for v in model.vars if v.name == "hb_h") == pytest.approx(0.0)


def test_disabled_technologies_are_forced_to_zero(monkeypatch):
    model = _build_model(
        monkeypatch,
        boiler=_technology(on_off=1, efficiency=0.9),
    )
    _optimize(model)

    for variable_name in (
        "power_chp",
        "power_heat_heat_pump",
        "power_eb",
        "power_bs",
        "power_hs",
        "power_ieh",
        "power_bm_hb",
        "power_bm_chp",
        "power_wte",
        "power_geo",
        "power_hp_river",
        "power_hp_wwtp",
    ):
        assert model.vars[variable_name].x == pytest.approx(0.0)

    assert model.vars["power_heat_boiler"].x > 0


@pytest.mark.parametrize(
    ("input_name", "capacity_name"),
    [
        ("industrial_eh", "power_ieh"),
        ("biomass_boiler", "power_bm_hb"),
        ("biomass_chp", "power_bm_chp"),
        ("waste_to_energy", "power_wte"),
        ("geothermal", "power_geo"),
        ("river_heat_pump", "power_hp_river"),
        ("wwtp_heat_pump", "power_hp_wwtp"),
    ],
)
def test_location_dependent_technologies_are_central_only(
    monkeypatch, input_name, capacity_name
):
    central_inputs = _base_model_inputs(
        boiler=_technology(on_off=1, efficiency=0.9), decentral_bool=0
    )
    central_inputs[input_name] = _technology(on_off=1)
    central = _build_model(monkeypatch, **central_inputs)
    central += central.vars[capacity_name] >= 1.0
    _optimize(central)

    decentral_inputs = _base_model_inputs(
        boiler=_technology(on_off=1, efficiency=0.9),
        heat_storage=_technology(on_off=1),
        decentral_bool=1,
    )
    decentral_inputs[input_name] = _technology(on_off=1)
    decentral = _optimize(_build_model(monkeypatch, **decentral_inputs))

    assert central.vars[capacity_name].x >= 1.0 - 1e-6
    assert decentral.vars[capacity_name].x == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("input_name", "limit_name", "constrained_flow_name"),
    [
        ("industrial_eh", "industrial_eh_energy_limit_mwh", "ieh_h"),
        ("biomass_boiler", "biomass_energy_limit_mwh", "bm_hb_f"),
        ("biomass_chp", "biomass_energy_limit_mwh", "bm_chp_f"),
        ("waste_to_energy", "wte_energy_limit_mwh", "wte_h"),
        ("geothermal", "geothermal_energy_limit_mwh", "geo_h"),
    ],
)
def test_resource_energy_limits_bound_preferred_technology(
    monkeypatch, input_name, limit_name, constrained_flow_name
):
    inputs = _base_model_inputs(
        boiler=_technology(on_off=1, efficiency=0.9),
        fuel_price=[0.1] * 3,
        fuel_price_biomass=[0.0] * 3,
        **{limit_name: 0.02},
    )
    inputs[input_name] = _technology(on_off=1, efficiency=1.0)

    model = _optimize(_build_model(monkeypatch, **inputs))

    assert sum(_values(model, constrained_flow_name)) == pytest.approx(20.0)


@pytest.mark.parametrize(
    ("input_name", "limit_name", "capacity_name", "heat_flow_name"),
    [
        (
            "river_heat_pump",
            "river_hp_capacity_limit_kw",
            "power_hp_river",
            "hp_river_h",
        ),
        (
            "wwtp_heat_pump",
            "wwtp_hp_capacity_limit_kw",
            "power_hp_wwtp",
            "hp_wwtp_h",
        ),
    ],
)
def test_resource_heat_pump_capacity_limits_bind_preferred_technology(
    monkeypatch, input_name, limit_name, capacity_name, heat_flow_name
):
    inputs = _base_model_inputs(
        boiler=_technology(on_off=1, efficiency=0.9),
        fuel_price=[0.1] * 3,
        **{limit_name: 5.0},
    )
    inputs[input_name] = _technology(on_off=1)

    model = _optimize(_build_model(monkeypatch, **inputs))

    assert model.vars[capacity_name].x == pytest.approx(5.0)
    assert sum(_values(model, heat_flow_name)) == pytest.approx(15.0)


def test_boiler_only_solution_matches_worked_reference(monkeypatch):
    inputs = _base_model_inputs(
        boiler=_technology(on_off=1, efficiency=0.9), fuel_price=[0.01] * 3
    )
    model = _optimize(_build_model(monkeypatch, **inputs))
    annual_cost_factor = annuity_factor(0.05, 20) * npv_factor(0.05, 20, 1.0)

    assert _values(model, "hb_h") == pytest.approx([10.0, 20.0, 15.0])
    assert _values(model, "hb_f") == pytest.approx([10 / 0.9, 20 / 0.9, 15 / 0.9])
    assert model.vars["power_heat_boiler"].x == pytest.approx(20.0)
    assert model.objective_value == pytest.approx(50.0 * 0.01 * annual_cost_factor)


def test_objective_contains_capex_fixed_fuel_and_variable_om_components(monkeypatch):
    base_inputs = _base_model_inputs(boiler=_technology(on_off=1, efficiency=0.9))
    base = _optimize(_build_model(monkeypatch, **base_inputs)).objective_value
    annuity = annuity_factor(base_inputs["interest_rate"], 20)
    npv_fixed = npv_factor(base_inputs["interest_rate"], 20, 1.0)
    annual_fuel = sum(base_inputs["demand_heat"]) / 0.9

    investment_inputs = deepcopy(base_inputs)
    investment_inputs["boiler"] = _technology(
        on_off=1, efficiency=0.9, reinvest_factor=0.2, residual_value_factor=0.1
    )
    investment_inputs["inv_cost"]["hb"]["central"] = _constant_cost(0.01)
    investment = _optimize(_build_model(monkeypatch, **investment_inputs)).objective_value
    assert investment - base == pytest.approx(20.0 * 0.01 * annuity * 1.1)

    fixed_inputs = deepcopy(base_inputs)
    fixed_inputs["fixed_cost"]["hb"]["central"] = _constant_cost(0.01)
    fixed = _optimize(_build_model(monkeypatch, **fixed_inputs)).objective_value
    assert fixed - base == pytest.approx(20.0 * 0.01 * annuity * npv_fixed)

    fuel_inputs = deepcopy(base_inputs)
    fuel_inputs["fuel_price"] = [0.01] * 3
    fuel = _optimize(_build_model(monkeypatch, **fuel_inputs)).objective_value
    assert fuel - base == pytest.approx(annual_fuel * 0.01 * annuity * npv_fixed)

    variable_om_inputs = deepcopy(base_inputs)
    variable_om_inputs["var_om_cost"]["hb"]["central"] = _constant_cost(0.01)
    variable_om = _optimize(
        _build_model(monkeypatch, **variable_om_inputs)
    ).objective_value
    assert variable_om - base == pytest.approx(
        annual_fuel * 0.01 * annuity * npv_fixed
    )


def test_objective_accounts_for_grid_purchases_and_feed_in_revenue(monkeypatch):
    inputs = _base_model_inputs(
        demand_heat=pd.Series([0.0, 0.0, 0.0]),
        demand_electric=pd.Series([1.0, 1.0, 1.0]),
        elec_price=[0.01] * 3,
    )
    grid_cost = _optimize(_build_model(monkeypatch, **inputs)).objective_value
    expected_grid_cost = 3.0 * 0.01 * annuity_factor(0.05, 20) * npv_factor(0.05, 20, 1.0)
    assert grid_cost == pytest.approx(expected_grid_cost)

    inputs["demand_electric"] = pd.Series([0.0, 0.0, 0.0])
    inputs["pv_infeed"] = pd.Series([1.0, 1.0, 1.0])
    inputs["elec_price"] = [0.0] * 3
    inputs["price_sell_pv"] = [0.01] * 3
    pv_revenue = _optimize(_build_model(monkeypatch, **inputs)).objective_value
    expected_pv_revenue = -3.0 * 0.01 * annuity_factor(0.05, 20) * npv_factor(
        0.05, 20, 1.0
    )
    assert pv_revenue == pytest.approx(expected_pv_revenue)


def test_objective_accounts_for_chp_feed_in_revenue(monkeypatch):
    base_inputs = _base_model_inputs(chp=_technology(on_off=1, power_to_heat_ratio=1.5))
    base = _optimize(_build_model(monkeypatch, **base_inputs)).objective_value

    revenue_inputs = deepcopy(base_inputs)
    revenue_inputs["price_sell_chp"] = [0.01] * 3
    revenue = _optimize(_build_model(monkeypatch, **revenue_inputs)).objective_value
    expected_revenue = (
        -(sum(base_inputs["demand_heat"]) / 1.5)
        * 0.01
        * annuity_factor(0.05, 20)
        * npv_factor(0.05, 20, 1.0)
    )
    assert revenue - base == pytest.approx(expected_revenue)


def test_annuity_and_npv_factors_match_reference_formulas():
    interest_rate = 0.05
    duration = 20
    annuity = annuity_factor(interest_rate, duration)
    expected_annuity = interest_rate / (1 - (1 + interest_rate) ** -duration)
    assert annuity == pytest.approx(expected_annuity)

    npv = npv_factor(interest_rate, duration, 1.0)
    expected_npv = (1 - (1 / (1 + interest_rate)) ** duration) / interest_rate
    assert npv == pytest.approx(expected_npv)

    # The equal-growth special case is the limit of the geometric series.
    assert npv_factor(interest_rate, duration, 1 + interest_rate) == pytest.approx(
        duration / (1 + interest_rate)
    )
