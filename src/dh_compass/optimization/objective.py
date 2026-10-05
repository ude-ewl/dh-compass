"""Named objective components for the optimization model."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from mip import LinExpr, Model, xsum

from ..economics.annuity import annuity_factor, npv_factor
from .model_inputs import ModelInputs
from .variables import ModelVariables


@dataclass(frozen=True)
class ObjectiveCostScalars:
    """Time-independent cost values used by the linear objective."""

    hs_inv_cost: float
    bs_inv_cost: float
    chp_inv_cost: float
    hb_inv_cost: float
    hp_inv_cost: float
    eb_inv_cost: float
    ieh_inv_cost: float
    bm_hb_inv_cost: float
    bm_chp_inv_cost: float
    wte_inv_cost: float
    geo_inv_cost: float
    hp_river_inv_cost: float
    hp_wwtp_inv_cost: float
    hs_fix_cost: float
    eb_fix_cost: float
    bs_fix_cost: float
    chp_fix_cost: float
    hb_fix_cost: float
    hp_fix_cost: float
    ieh_fix_cost: float
    bm_hb_fix_cost: float
    bm_chp_fix_cost: float
    wte_fix_cost: float
    geo_fix_cost: float
    hp_river_fix_cost: float
    hp_wwtp_fix_cost: float
    chp_om_cost: float
    hb_om_cost: float
    ieh_om_cost: float
    bm_hb_om_cost: float
    bm_chp_om_cost: float
    wte_om_cost: float
    geo_om_cost: float


@dataclass(frozen=True)
class ObjectiveComponents:
    """The independently named linear objective components."""

    investment_costs: LinExpr
    fixed_costs: LinExpr
    operational_costs: LinExpr

    @property
    def annualized_investment_cost(self) -> LinExpr:
        """Alias using the terminology from the refactoring plan."""

        return self.investment_costs

    @property
    def fixed_operating_cost(self) -> LinExpr:
        """Alias for fixed capacity-based operating costs."""

        return self.fixed_costs

    @property
    def variable_operating_cost(self) -> LinExpr:
        """Alias for time-dependent operating costs and revenues."""

        return self.operational_costs

    @property
    def total(self) -> LinExpr:
        """Return the objective in the legacy component order."""

        return self.investment_costs + self.operational_costs + self.fixed_costs


def _cost_scalars(inputs: ModelInputs) -> ObjectiveCostScalars:
    """Evaluate capacity-based cost curves at the legacy reference peaks."""

    economic = inputs.economic
    technologies = inputs.technologies
    decentral = inputs.options.decentral_bool == 1
    heat_peak = int(np.amax(inputs.demand.demand_heat))
    electric_peak = int(np.amax(inputs.demand.demand_electric))

    chp_power_to_heat_ratio = [
        technologies.chp[index]["power_to_heat_ratio"]
        for index in range(len(technologies.chp))
    ]
    biomass_chp_power_to_heat_ratio = [
        technologies.biomass_chp[index]["power_to_heat_ratio"]
        for index in range(len(technologies.biomass_chp))
    ]

    inv_cost = economic.inv_cost
    fixed_cost = economic.fixed_cost
    var_om_cost = economic.var_om_cost

    hb_inv_costs = inv_cost["hb"]["decentral" if decentral else "central"]
    hs_inv_costs = inv_cost["hs"]["decentral" if decentral else "central"]
    hp_inv_costs = inv_cost["hp"]["decentral" if decentral else "central"]
    hb_fixed_costs = fixed_cost["hb"]["decentral" if decentral else "central"]
    hp_fixed_costs = fixed_cost["hp"]["decentral" if decentral else "central"]

    # These mode selections and reference capacities intentionally match the
    # former model builder, including its central reference for boiler O&M.
    return ObjectiveCostScalars(
        hs_inv_cost=hs_inv_costs(heat_peak),
        bs_inv_cost=inv_cost["bs"](electric_peak),
        chp_inv_cost=inv_cost["chp"](
            int(heat_peak * 0.3 / chp_power_to_heat_ratio[0])
        ),
        hb_inv_cost=hb_inv_costs(heat_peak),
        hp_inv_cost=hp_inv_costs(heat_peak),
        eb_inv_cost=inv_cost["eb"](heat_peak),
        ieh_inv_cost=inv_cost["ieh"](heat_peak),
        bm_hb_inv_cost=inv_cost["bm_hb"](heat_peak),
        bm_chp_inv_cost=(
            inv_cost["bm_chp"](
                int(heat_peak * 0.3 / biomass_chp_power_to_heat_ratio[0])
            )
            if biomass_chp_power_to_heat_ratio
            else inv_cost["bm_chp"](heat_peak)
        ),
        wte_inv_cost=inv_cost["wte"](heat_peak),
        geo_inv_cost=inv_cost["geo"](heat_peak),
        hp_river_inv_cost=inv_cost["hp_river"](heat_peak),
        hp_wwtp_inv_cost=inv_cost["hp_wwtp"](heat_peak),
        hs_fix_cost=fixed_cost["hs"](heat_peak),
        eb_fix_cost=fixed_cost["eb"](heat_peak),
        bs_fix_cost=fixed_cost["bs"](electric_peak),
        chp_fix_cost=fixed_cost["chp"](
            int(heat_peak * 0.3 / chp_power_to_heat_ratio[0])
        ),
        hb_fix_cost=hb_fixed_costs(heat_peak),
        hp_fix_cost=hp_fixed_costs(heat_peak),
        ieh_fix_cost=fixed_cost["ieh"](heat_peak),
        bm_hb_fix_cost=fixed_cost["bm_hb"](heat_peak),
        bm_chp_fix_cost=(
            fixed_cost["bm_chp"](
                int(heat_peak * 0.3 / biomass_chp_power_to_heat_ratio[0])
            )
            if biomass_chp_power_to_heat_ratio
            else fixed_cost["bm_chp"](heat_peak)
        ),
        wte_fix_cost=fixed_cost["wte"](heat_peak),
        geo_fix_cost=fixed_cost["geo"](heat_peak),
        hp_river_fix_cost=fixed_cost["hp_river"](heat_peak),
        hp_wwtp_fix_cost=fixed_cost["hp_wwtp"](heat_peak),
        chp_om_cost=var_om_cost["chp"](
            int(heat_peak * 0.3 / chp_power_to_heat_ratio[0])
        ),
        hb_om_cost=var_om_cost["hb"]["central"](heat_peak),
        ieh_om_cost=var_om_cost["ieh"](heat_peak),
        bm_hb_om_cost=var_om_cost["bm_hb"](heat_peak),
        bm_chp_om_cost=(
            var_om_cost["bm_chp"](
                int(heat_peak * 0.3 / biomass_chp_power_to_heat_ratio[0])
            )
            if biomass_chp_power_to_heat_ratio
            else var_om_cost["bm_chp"](heat_peak)
        ),
        wte_om_cost=var_om_cost["wte"](heat_peak),
        geo_om_cost=var_om_cost["geo"](heat_peak),
    )


def _npv_factors(inputs: ModelInputs) -> dict[str, float]:
    """Return the escalation factors used by the objective."""

    economic = inputs.economic
    return {
        "pv": npv_factor(
            economic.interest_rate,
            economic.investment_duration,
            economic.pv_rem_annual_change,
        ),
        "chp": npv_factor(
            economic.interest_rate,
            economic.investment_duration,
            economic.chp_rem_annual_change,
        ),
        "elec": npv_factor(
            economic.interest_rate,
            economic.investment_duration,
            economic.electricity_price_annual_change,
        ),
        "gas": npv_factor(
            economic.interest_rate,
            economic.investment_duration,
            economic.gas_price_annual_change,
        ),
        "fixed": npv_factor(
            economic.interest_rate,
            economic.investment_duration,
            annual_change=1,
        ),
    }


def build_objective(
    inputs: ModelInputs, variables: ModelVariables
) -> ObjectiveComponents:
    """Build investment, fixed, and operational objective expressions."""

    economic = inputs.economic
    market = inputs.market
    options = inputs.options
    decentral = options.decentral_bool
    ref_binary = options.ref_binary
    indices = variables.indices
    scalars = _cost_scalars(inputs)
    annuity = annuity_factor(economic.interest_rate, economic.investment_duration)
    npv = _npv_factors(inputs)

    battery = variables.battery
    chp = variables.chp
    heat_storage = variables.heat_storage
    boiler = variables.boiler
    heat_pump = variables.heat_pump
    electrode = variables.electrode_boiler
    excess_heat = variables.industrial_excess_heat
    biomass_boiler = variables.biomass_boiler
    biomass_chp = variables.biomass_chp
    waste = variables.waste_to_energy
    geothermal = variables.geothermal
    river = variables.river_heat_pump
    wwtp = variables.wwtp_heat_pump

    investment_costs = (
        xsum(
            (1 - decentral)
            * annuity
            * (
                heat_storage.capacity_hs[index]
                * scalars.hs_inv_cost
                * (
                    1
                    + inputs.technologies.heat_storage[index]["reinvest_factor"]
                    - inputs.technologies.heat_storage[index]["residual_value_factor"]
                )
            )
            for index in indices.heat_storage
        )
        + xsum(
            annuity
            * (
                battery.capacity_bs[index]
                * scalars.bs_inv_cost
                * (
                    1
                    + inputs.technologies.battery_storage[index]["reinvest_factor"]
                    - inputs.technologies.battery_storage[index]["residual_value_factor"]
                )
            )
            for index in indices.battery
        )
        + xsum(
            annuity
            * (
                chp.power_chp[index]
                * scalars.chp_inv_cost
                * (
                    1
                    + inputs.technologies.chp[index]["reinvest_factor"]
                    - inputs.technologies.chp[index]["residual_value_factor"]
                )
            )
            for index in indices.chp
        )
        + xsum(
            annuity
            * (
                boiler.power_heat_boiler[index]
                * scalars.hb_inv_cost
                * (
                    (1 - ref_binary)
                    + inputs.technologies.boiler[index]["reinvest_factor"]
                    - inputs.technologies.boiler[index]["residual_value_factor"]
                )
            )
            for index in indices.boiler
        )
        + xsum(
            annuity
            * (
                heat_pump.power_heat_heat_pump[index]
                * scalars.hp_inv_cost
                * (
                    1
                    + inputs.technologies.heat_pump[index]["reinvest_factor"]
                    - inputs.technologies.heat_pump[index]["residual_value_factor"]
                )
            )
            for index in indices.heat_pump
        )
        + xsum(
            (1 - decentral)
            * annuity
            * (
                electrode.power_eb[index]
                * scalars.eb_inv_cost
                * (
                    1
                    + inputs.technologies.electrode_boiler[index]["reinvest_factor"]
                    - inputs.technologies.electrode_boiler[index]["residual_value_factor"]
                )
            )
            for index in indices.electrode_boiler
        )
        + xsum(
            (1 - decentral)
            * annuity
            * (
                excess_heat.power_ieh[index]
                * scalars.ieh_inv_cost
                * (
                    1
                    + inputs.technologies.industrial_eh[index]["reinvest_factor"]
                    - inputs.technologies.industrial_eh[index]["residual_value_factor"]
                )
            )
            for index in indices.industrial_eh
        )
        + xsum(
            (1 - decentral)
            * annuity
            * (
                biomass_boiler.power_bm_hb[index]
                * scalars.bm_hb_inv_cost
                * (
                    1
                    + inputs.technologies.biomass_boiler[index]["reinvest_factor"]
                    - inputs.technologies.biomass_boiler[index]["residual_value_factor"]
                )
            )
            for index in indices.biomass_boiler
        )
        + xsum(
            (1 - decentral)
            * annuity
            * (
                biomass_chp.power_bm_chp[index]
                * scalars.bm_chp_inv_cost
                * (
                    1
                    + inputs.technologies.biomass_chp[index]["reinvest_factor"]
                    - inputs.technologies.biomass_chp[index]["residual_value_factor"]
                )
            )
            for index in indices.biomass_chp
        )
        + xsum(
            (1 - decentral)
            * annuity
            * (
                waste.power_wte[index]
                * scalars.wte_inv_cost
                * (
                    1
                    + inputs.technologies.waste_to_energy[index]["reinvest_factor"]
                    - inputs.technologies.waste_to_energy[index]["residual_value_factor"]
                )
            )
            for index in indices.waste_to_energy
        )
        + xsum(
            (1 - decentral)
            * annuity
            * (
                geothermal.power_geo[index]
                * scalars.geo_inv_cost
                * (
                    1
                    + inputs.technologies.geothermal[index]["reinvest_factor"]
                    - inputs.technologies.geothermal[index]["residual_value_factor"]
                )
            )
            for index in indices.geothermal
        )
        + xsum(
            (1 - decentral)
            * annuity
            * (
                river.power[index]
                * scalars.hp_river_inv_cost
                * (
                    1
                    + inputs.technologies.river_heat_pump[index]["reinvest_factor"]
                    - inputs.technologies.river_heat_pump[index]["residual_value_factor"]
                )
            )
            for index in indices.river_heat_pump
        )
        + xsum(
            (1 - decentral)
            * annuity
            * (
                wwtp.power[index]
                * scalars.hp_wwtp_inv_cost
                * (
                    1
                    + inputs.technologies.wwtp_heat_pump[index]["reinvest_factor"]
                    - inputs.technologies.wwtp_heat_pump[index]["residual_value_factor"]
                )
            )
            for index in indices.wwtp_heat_pump
        )
    )

    fixed_costs = (
        xsum(
            (1 - decentral)
            * annuity
            * npv["fixed"]
            * heat_storage.power_hs[index]
            * scalars.hs_fix_cost
            for index in indices.heat_storage
        )
        + xsum(
            (1 - decentral)
            * annuity
            * npv["fixed"]
            * electrode.power_eb[index]
            * scalars.eb_fix_cost
            for index in indices.electrode_boiler
        )
        + xsum(
            annuity * npv["fixed"] * battery.power_bs[index] * scalars.bs_fix_cost
            for index in indices.battery
        )
        + xsum(
            annuity * npv["fixed"] * chp.power_chp[index] * scalars.chp_fix_cost
            for index in indices.chp
        )
        + xsum(
            annuity
            * npv["fixed"]
            * boiler.power_heat_boiler[index]
            * scalars.hb_fix_cost
            for index in indices.boiler
        )
        + xsum(
            annuity
            * npv["fixed"]
            * heat_pump.power_heat_heat_pump[index]
            * scalars.hp_fix_cost
            for index in indices.heat_pump
        )
        + xsum(
            (1 - decentral)
            * annuity
            * npv["fixed"]
            * excess_heat.power_ieh[index]
            * scalars.ieh_fix_cost
            for index in indices.industrial_eh
        )
        + xsum(
            (1 - decentral)
            * annuity
            * npv["fixed"]
            * biomass_boiler.power_bm_hb[index]
            * scalars.bm_hb_fix_cost
            for index in indices.biomass_boiler
        )
        + xsum(
            (1 - decentral)
            * annuity
            * npv["fixed"]
            * biomass_chp.power_bm_chp[index]
            * scalars.bm_chp_fix_cost
            for index in indices.biomass_chp
        )
        + xsum(
            (1 - decentral)
            * annuity
            * npv["fixed"]
            * waste.power_wte[index]
            * scalars.wte_fix_cost
            for index in indices.waste_to_energy
        )
        + xsum(
            (1 - decentral)
            * annuity
            * npv["fixed"]
            * geothermal.power_geo[index]
            * scalars.geo_fix_cost
            for index in indices.geothermal
        )
        + xsum(
            (1 - decentral)
            * annuity
            * npv["fixed"]
            * river.power[index]
            * scalars.hp_river_fix_cost
            for index in indices.river_heat_pump
        )
        + xsum(
            (1 - decentral)
            * annuity
            * npv["fixed"]
            * wwtp.power[index]
            * scalars.hp_wwtp_fix_cost
            for index in indices.wwtp_heat_pump
        )
    )

    operational_costs = xsum(
        -variables.flows.y_S_PV[time_index]
        * market.price_sell_pv[time_index]
        * market.dt
        * npv["pv"]
        * annuity
        + -variables.flows.y_S_CHP[time_index]
        * market.price_sell_chp[time_index]
        * market.dt
        * npv["chp"]
        * annuity
        + variables.flows.z_D[time_index]
        * market.elec_price[time_index]
        * market.dt
        * npv["elec"]
        * annuity
        + xsum(
            chp.chp_f[time_index][index]
            * (market.fuel_price[time_index] + scalars.chp_om_cost)
            * market.dt
            * npv["gas"]
            * annuity
            for index in indices.chp
        )
        + xsum(
            boiler.hb_f[time_index][index]
            * (market.fuel_price[time_index] + scalars.hb_om_cost)
            * market.dt
            * npv["gas"]
            * annuity
            for index in indices.boiler
        )
        + xsum(
            excess_heat.ieh_h[time_index][index]
            * scalars.ieh_om_cost
            * market.dt
            * npv["fixed"]
            * annuity
            for index in indices.industrial_eh
        )
        + xsum(
            biomass_boiler.bm_hb_f[time_index][index]
            * (market.fuel_price_biomass[time_index] + scalars.bm_hb_om_cost)
            * market.dt
            * npv["gas"]
            * annuity
            for index in indices.biomass_boiler
        )
        + xsum(
            biomass_chp.bm_chp_f[time_index][index]
            * (market.fuel_price_biomass[time_index] + scalars.bm_chp_om_cost)
            * market.dt
            * npv["gas"]
            * annuity
            for index in indices.biomass_chp
        )
        + -variables.flows.y_S_BM_CHP[time_index]
        * market.price_sell_chp[time_index]
        * market.dt
        * npv["chp"]
        * annuity
        + xsum(
            waste.wte_h[time_index][index]
            * scalars.wte_om_cost
            * market.dt
            * npv["fixed"]
            * annuity
            for index in indices.waste_to_energy
        )
        + xsum(
            geothermal.geo_h[time_index][index]
            * scalars.geo_om_cost
            * market.dt
            * npv["fixed"]
            * annuity
            for index in indices.geothermal
        )
        + variables.flows.heat_dumped[time_index] * 0.1
        for time_index in indices.time
    )

    return ObjectiveComponents(
        investment_costs=investment_costs,
        fixed_costs=fixed_costs,
        operational_costs=operational_costs,
    )


def add_objective(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> ObjectiveComponents:
    """Build and assign the objective, returning its named components."""

    components = build_objective(inputs, variables)
    model.objective = components.total
    return components


__all__ = [
    "ObjectiveComponents",
    "ObjectiveCostScalars",
    "add_objective",
    "annuity_factor",
    "build_objective",
    "npv_factor",
]
