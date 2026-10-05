"""Cost calculations for solver-independent reporting results.

The optimization model computes the objective used to make decisions.  This
module reconstructs a readable cost breakdown from a value-only portfolio for
reports and viewer output.  It deliberately does not know about solver models.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from ..economics.annuity import annuity_factor, npv_factor
from ..optimization.context import OptimizationContext

CostFunction = Callable[[int], float]
Portfolio = Mapping[str, object]


def _annualized_investment_cost(
    capacity: float,
    cost_function: CostFunction,
    technology_config: Mapping[str, object],
    annuity: float,
) -> float:
    unit_cost = cost_function(int(capacity))
    reinvestment_factor = technology_config.get("reinvest_factor", 0)
    residual_value_factor = technology_config.get("residual_value_factor", 0)
    return capacity * unit_cost * annuity * (
        1 + reinvestment_factor - residual_value_factor
    )


def _annualized_fixed_cost(
    capacity: float,
    cost_function: CostFunction,
    annuity: float,
    fixed_npv: float,
) -> float:
    return capacity * cost_function(int(capacity)) * annuity * fixed_npv


def compute_investment_costs(
    portfolio: Portfolio,
    ctx: OptimizationContext,
    decentral_bool: bool = False,
) -> dict[str, float]:
    """Calculate annualized investment costs by technology.

    The capacity and cost-curve choices intentionally mirror the optimization
    model's reporting behavior.  In particular, the returned values are a
    presentation breakdown and are not substituted for the model objective.
    """

    economic = ctx.economic
    technologies = ctx.technologies.for_model(decentral_bool)
    inv_cost = economic.inv_cost
    af = annuity_factor(economic.interest_rate, economic.investment_duration)
    supply = portfolio.get("supply", {})
    storage = portfolio.get("storage", {})
    costs: dict[str, float] = {}

    if "heat_pump" in supply:
        cap = supply["heat_pump"]["capacity_kw"]
        if cap > 0:
            tech_cfg = technologies.heat_pump[0]
            cost_fn = inv_cost["hp"]["decentral" if decentral_bool else "central"]
            costs["heat_pump"] = _annualized_investment_cost(
                cap, cost_fn, tech_cfg, af
            )

    if "boiler" in supply:
        cap = supply["boiler"]["capacity_kw"]
        if cap > 0:
            tech_cfg = technologies.boiler[0]
            cost_fn = inv_cost["hb"]["decentral" if decentral_bool else "central"]
            costs["boiler"] = _annualized_investment_cost(
                cap, cost_fn, tech_cfg, af
            )

    if "chp" in supply:
        cap_el = supply["chp"]["capacity_el_kw"]
        if cap_el > 0:
            tech_cfg = technologies.chp[0]
            costs["chp"] = _annualized_investment_cost(
                cap_el, inv_cost["chp"], tech_cfg, af
            )

    if "electrode_boiler" in supply:
        cap = supply["electrode_boiler"]["capacity_kw"]
        if cap > 0 and not decentral_bool:
            tech_cfg = technologies.electrode_boiler[0]
            costs["electrode_boiler"] = _annualized_investment_cost(
                cap, inv_cost["eb"], tech_cfg, af
            )

    if "industrial_excess_heat" in supply:
        cap = supply["industrial_excess_heat"]["capacity_kw"]
        if cap > 0 and not decentral_bool:
            tech_cfg = technologies.industrial_eh[0]
            costs["industrial_excess_heat"] = _annualized_investment_cost(
                cap, inv_cost["ieh"], tech_cfg, af
            )

    if "biomass_boiler" in supply:
        cap = supply["biomass_boiler"]["capacity_kw"]
        if cap > 0 and not decentral_bool:
            tech_cfg = technologies.biomass_boiler[0]
            costs["biomass_boiler"] = _annualized_investment_cost(
                cap, inv_cost["bm_hb"], tech_cfg, af
            )

    if "biomass_chp" in supply:
        cap_el = supply["biomass_chp"]["capacity_el_kw"]
        if cap_el > 0 and not decentral_bool:
            tech_cfg = technologies.biomass_chp[0]
            costs["biomass_chp"] = _annualized_investment_cost(
                cap_el, inv_cost["bm_chp"], tech_cfg, af
            )

    if "waste_to_energy" in supply:
        cap = supply["waste_to_energy"]["capacity_kw"]
        if cap > 0 and not decentral_bool:
            tech_cfg = technologies.waste_to_energy[0]
            costs["waste_to_energy"] = _annualized_investment_cost(
                cap, inv_cost["wte"], tech_cfg, af
            )

    if "geothermal" in supply:
        cap = supply["geothermal"]["capacity_kw"]
        if cap > 0 and not decentral_bool:
            tech_cfg = technologies.geothermal[0]
            costs["geothermal"] = _annualized_investment_cost(
                cap, inv_cost["geo"], tech_cfg, af
            )

    if "river_heat_pump" in supply:
        cap = supply["river_heat_pump"]["capacity_kw"]
        if cap > 0 and not decentral_bool:
            tech_cfg = technologies.river_heat_pump[0]
            costs["river_heat_pump"] = _annualized_investment_cost(
                cap, inv_cost["hp_river"], tech_cfg, af
            )

    if "wwtp_heat_pump" in supply:
        cap = supply["wwtp_heat_pump"]["capacity_kw"]
        if cap > 0 and not decentral_bool:
            tech_cfg = technologies.wwtp_heat_pump[0]
            costs["wwtp_heat_pump"] = _annualized_investment_cost(
                cap, inv_cost["hp_wwtp"], tech_cfg, af
            )

    if "heat_storage" in storage:
        cap = storage["heat_storage"]["capacity_kwh"]
        if cap > 0 and not decentral_bool:
            tech_cfg = technologies.heat_storage[0]
            cost_fn = inv_cost["hs"]["central"]
            pwr = storage["heat_storage"]["power_kw"]
            uc = cost_fn(int(pwr)) if pwr > 0 else 0
            rf = tech_cfg.get("reinvest_factor", 0)
            rv = tech_cfg.get("residual_value_factor", 0)
            costs["heat_storage"] = cap * uc * af * (1 + rf - rv)

    if "battery_storage" in storage:
        cap = storage["battery_storage"]["capacity_kwh"]
        if cap > 0:
            tech_cfg = technologies.battery_storage[0]
            cost_fn = inv_cost["bs"]
            pwr = storage["battery_storage"]["power_kw"]
            uc = cost_fn(int(pwr)) if pwr > 0 else 0
            rf = tech_cfg.get("reinvest_factor", 0)
            rv = tech_cfg.get("residual_value_factor", 0)
            costs["battery_storage"] = cap * uc * af * (1 + rf - rv)

    return costs


def compute_fixed_costs(
    portfolio: Portfolio,
    ctx: OptimizationContext,
    decentral_bool: bool = False,
) -> dict[str, float]:
    """Calculate annualized fixed O&M costs by technology."""

    economic = ctx.economic
    fixed_cost = economic.fixed_cost
    af = annuity_factor(economic.interest_rate, economic.investment_duration)
    npv_fixed = npv_factor(economic.interest_rate, economic.investment_duration, 1.0)
    supply = portfolio.get("supply", {})
    storage = portfolio.get("storage", {})
    costs: dict[str, float] = {}

    if "heat_pump" in supply and supply["heat_pump"]["capacity_kw"] > 0:
        cap = supply["heat_pump"]["capacity_kw"]
        fn = (
            fixed_cost["hp"]["decentral"]
            if decentral_bool
            else fixed_cost["hp"]["central"]
        )
        costs["heat_pump"] = _annualized_fixed_cost(cap, fn, af, npv_fixed)

    if "boiler" in supply and supply["boiler"]["capacity_kw"] > 0:
        cap = supply["boiler"]["capacity_kw"]
        fn = (
            fixed_cost["hb"]["decentral"]
            if decentral_bool
            else fixed_cost["hb"]["central"]
        )
        costs["boiler"] = _annualized_fixed_cost(cap, fn, af, npv_fixed)

    if "chp" in supply and supply["chp"]["capacity_el_kw"] > 0:
        cap = supply["chp"]["capacity_el_kw"]
        costs["chp"] = _annualized_fixed_cost(
            cap, fixed_cost["chp"], af, npv_fixed
        )

    if (
        "electrode_boiler" in supply
        and supply["electrode_boiler"]["capacity_kw"] > 0
        and not decentral_bool
    ):
        cap = supply["electrode_boiler"]["capacity_kw"]
        costs["electrode_boiler"] = _annualized_fixed_cost(
            cap, fixed_cost["eb"], af, npv_fixed
        )

    if (
        "industrial_excess_heat" in supply
        and supply["industrial_excess_heat"]["capacity_kw"] > 0
        and not decentral_bool
    ):
        cap = supply["industrial_excess_heat"]["capacity_kw"]
        costs["industrial_excess_heat"] = _annualized_fixed_cost(
            cap, fixed_cost["ieh"], af, npv_fixed
        )

    if (
        "biomass_boiler" in supply
        and supply["biomass_boiler"]["capacity_kw"] > 0
        and not decentral_bool
    ):
        cap = supply["biomass_boiler"]["capacity_kw"]
        costs["biomass_boiler"] = _annualized_fixed_cost(
            cap, fixed_cost["bm_hb"], af, npv_fixed
        )

    if (
        "biomass_chp" in supply
        and supply["biomass_chp"]["capacity_el_kw"] > 0
        and not decentral_bool
    ):
        cap = supply["biomass_chp"]["capacity_el_kw"]
        costs["biomass_chp"] = _annualized_fixed_cost(
            cap, fixed_cost["bm_chp"], af, npv_fixed
        )

    if (
        "waste_to_energy" in supply
        and supply["waste_to_energy"]["capacity_kw"] > 0
        and not decentral_bool
    ):
        cap = supply["waste_to_energy"]["capacity_kw"]
        costs["waste_to_energy"] = _annualized_fixed_cost(
            cap, fixed_cost["wte"], af, npv_fixed
        )

    if (
        "geothermal" in supply
        and supply["geothermal"]["capacity_kw"] > 0
        and not decentral_bool
    ):
        cap = supply["geothermal"]["capacity_kw"]
        costs["geothermal"] = _annualized_fixed_cost(
            cap, fixed_cost["geo"], af, npv_fixed
        )

    if (
        "river_heat_pump" in supply
        and supply["river_heat_pump"]["capacity_kw"] > 0
        and not decentral_bool
    ):
        cap = supply["river_heat_pump"]["capacity_kw"]
        costs["river_heat_pump"] = _annualized_fixed_cost(
            cap, fixed_cost["hp_river"], af, npv_fixed
        )

    if (
        "wwtp_heat_pump" in supply
        and supply["wwtp_heat_pump"]["capacity_kw"] > 0
        and not decentral_bool
    ):
        cap = supply["wwtp_heat_pump"]["capacity_kw"]
        costs["wwtp_heat_pump"] = _annualized_fixed_cost(
            cap, fixed_cost["hp_wwtp"], af, npv_fixed
        )

    if (
        "heat_storage" in storage
        and storage["heat_storage"]["power_kw"] > 0
        and not decentral_bool
    ):
        cap = storage["heat_storage"]["power_kw"]
        costs["heat_storage"] = _annualized_fixed_cost(
            cap, fixed_cost["hs"], af, npv_fixed
        )

    if "battery_storage" in storage and storage["battery_storage"]["power_kw"] > 0:
        cap = storage["battery_storage"]["power_kw"]
        costs["battery_storage"] = _annualized_fixed_cost(
            cap, fixed_cost["bs"], af, npv_fixed
        )

    return costs


def compute_operational_costs(
    portfolio: Portfolio,
    ctx: OptimizationContext,
    decentral_bool: bool = False,
) -> dict[str, float]:
    """Calculate annual operating costs and feed-in revenues."""

    market = ctx.market.for_model(decentral_bool)
    var_om_cost = ctx.economic.var_om_cost
    fuel_price = market.fuel_price
    elec_price = market.elec_price

    avg_fuel = sum(fuel_price) / len(fuel_price) if fuel_price else 0
    avg_elec = sum(elec_price) / len(elec_price) if elec_price else 0
    avg_pv = sum(market.price_sell_pv) / len(market.price_sell_pv) if market.price_sell_pv else 0
    avg_chp = (
        sum(market.price_sell_chp) / len(market.price_sell_chp)
        if market.price_sell_chp
        else 0
    )

    chp_om = var_om_cost["chp"](int(1)) if var_om_cost.get("chp") else 0
    hb_om = 0
    if not decentral_bool and var_om_cost.get("hb", {}).get("central"):
        hb_om = var_om_cost["hb"]["central"](int(1))

    bm_hb_om = var_om_cost["bm_hb"](int(1)) if var_om_cost.get("bm_hb") else 0
    bm_chp_om = var_om_cost["bm_chp"](int(1)) if var_om_cost.get("bm_chp") else 0
    avg_bm_fuel = (
        sum(market.fuel_price_biomass) / len(market.fuel_price_biomass)
        if market.fuel_price_biomass
        else 0
    )

    fuel_boiler = portfolio.get("fuel_boiler_kwh", 0) * (avg_fuel + hb_om)
    fuel_chp = portfolio.get("fuel_chp_kwh", 0) * (avg_fuel + chp_om)
    fuel_bm = (
        portfolio.get("fuel_biomass_boiler_kwh", 0) * (avg_bm_fuel + bm_hb_om)
        + portfolio.get("fuel_biomass_chp_kwh", 0) * (avg_bm_fuel + bm_chp_om)
    )
    elec = portfolio.get("elec_grid_kwh", 0) * avg_elec
    pv_rev = portfolio.get("pv_feed_in_kwh", 0) * avg_pv
    chp_rev = portfolio.get("chp_feed_in_kwh", 0) * avg_chp
    bm_chp_rev = portfolio.get("biomass_chp_feed_in_kwh", 0) * avg_chp

    return {
        "fuel_boiler_annual_eur": round(fuel_boiler, 2),
        "fuel_chp_annual_eur": round(fuel_chp, 2),
        "fuel_biomass_annual_eur": round(fuel_bm, 2),
        "electricity_annual_eur": round(elec, 2),
        "pv_revenue_annual_eur": round(pv_rev, 2),
        "chp_revenue_annual_eur": round(chp_rev, 2),
        "biomass_chp_revenue_annual_eur": round(bm_chp_rev, 2),
        "net_operational_annual_eur": round(
            fuel_boiler + fuel_chp + fuel_bm + elec - pv_rev - chp_rev - bm_chp_rev,
            2,
        ),
    }


def build_cost_breakdown(
    portfolio: Portfolio,
    ctx: OptimizationContext,
    decentral_bool: bool = False,
) -> dict[str, object]:
    """Build the documented supply cost-breakdown structure."""

    investment = compute_investment_costs(portfolio, ctx, decentral_bool)
    fixed = compute_fixed_costs(portfolio, ctx, decentral_bool)
    operational = compute_operational_costs(portfolio, ctx, decentral_bool)

    total_investment = sum(investment.values())
    total_fixed = sum(fixed.values())
    net_operational = operational["net_operational_annual_eur"]
    total_breakdown = total_investment + total_fixed + net_operational

    return {
        "investment": {
            "by_technology_eur": {
                key: round(value, 2) for key, value in investment.items()
            },
            "total_eur": round(total_investment, 2),
        },
        "fixed_om": {
            "by_technology_eur": {
                key: round(value, 2) for key, value in fixed.items()
            },
            "total_eur": round(total_fixed, 2),
        },
        "operational": operational,
        "breakdown_total_eur": round(total_breakdown, 2),
        "note": (
            "Breakdown is reconstructed from model variables; for exact totals "
            "use the model objective values."
        ),
    }


__all__ = [
    "build_cost_breakdown",
    "compute_fixed_costs",
    "compute_investment_costs",
    "compute_operational_costs",
]
