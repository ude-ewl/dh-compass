from types import SimpleNamespace

import numpy as np
import pytest

from dh_compass.economics.annuity import annuity_factor, npv_factor
from dh_compass.reporting.costs import (
    build_cost_breakdown,
    compute_fixed_costs,
    compute_investment_costs,
    compute_operational_costs,
)
from dh_compass.reporting.json_export import to_native


def _context():
    technologies = SimpleNamespace(
        boiler=[{"reinvest_factor": 0.1, "residual_value_factor": 0.2}]
    )
    central_market = SimpleNamespace(
        fuel_price=[3.0],
        elec_price=[4.0],
        fuel_price_biomass=[],
        price_sell_pv=[0.2],
        price_sell_chp=[0.3],
    )
    decentral_market = SimpleNamespace(
        fuel_price=[4.0],
        elec_price=[5.0],
        fuel_price_biomass=[],
        price_sell_pv=[0.2],
        price_sell_chp=[0.3],
    )
    return SimpleNamespace(
        economic=SimpleNamespace(
            interest_rate=0.05,
            investment_duration=20,
            inv_cost={"hb": {"central": lambda _: 100.0, "decentral": lambda _: 90.0}},
            fixed_cost={"hb": {"central": lambda _: 2.0, "decentral": lambda _: 3.0}},
            var_om_cost={"hb": {"central": lambda _: 0.5}},
        ),
        market=SimpleNamespace(
            for_model=lambda decentral: decentral_market if decentral else central_market
        ),
        technologies=SimpleNamespace(for_model=lambda _decentral: technologies),
    )


def _portfolio():
    return {
        "supply": {"boiler": {"capacity_kw": 10.0}},
        "storage": {},
        "fuel_boiler_kwh": 100.0,
        "elec_grid_kwh": 25.0,
        "pv_feed_in_kwh": 10.0,
    }


def test_cost_components_are_independent_of_schema_assembly():
    context = _context()
    portfolio = _portfolio()
    annuity = annuity_factor(
        context.economic.interest_rate,
        context.economic.investment_duration,
    )
    fixed_npv = npv_factor(
        context.economic.interest_rate,
        context.economic.investment_duration,
        1.0,
    )

    investment = compute_investment_costs(portfolio, context)
    fixed = compute_fixed_costs(portfolio, context)
    operational = compute_operational_costs(portfolio, context)

    assert investment == {"boiler": pytest.approx(10 * 100 * annuity * 0.9)}
    assert fixed == {"boiler": pytest.approx(10 * 2 * annuity * fixed_npv)}
    assert operational["fuel_boiler_annual_eur"] == 350.0
    assert operational["electricity_annual_eur"] == 100.0
    assert operational["pv_revenue_annual_eur"] == 2.0
    assert operational["net_operational_annual_eur"] == 448.0

    breakdown = build_cost_breakdown(portfolio, context)
    assert breakdown["investment"]["by_technology_eur"] == {
        "boiler": round(investment["boiler"], 2)
    }
    assert breakdown["fixed_om"]["by_technology_eur"] == {
        "boiler": round(fixed["boiler"], 2)
    }
    assert breakdown["operational"] == operational


def test_native_conversion_is_deferred_to_json_boundary():
    value = {"values": np.array([np.int64(2), np.nan])}

    assert to_native(value) == {"values": [2, None]}
