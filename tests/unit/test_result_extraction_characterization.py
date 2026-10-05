from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dh_compass.optimization.result_extraction import extract_model_portfolio


@dataclass
class FakeVariable:
    name: str
    x: float


class FakeModel:
    def __init__(self, variables):
        self.vars = variables


def _fake_model() -> FakeModel:
    values = {
        "power_heat_heat_pump": [12.3456],
        "power_heat_boiler": [10.0],
        "power_chp": [2.5],
        "power_heat_chp": [3.85],
        "power_eb": [4.0],
        "power_ieh": [5.0],
        "power_bm_hb": [6.0],
        "power_bm_chp": [1.25],
        "power_heat_bm_chp": [6.25],
        "power_wte": [7.0],
        "power_geo": [8.0],
        "power_hp_river": [9.0],
        "power_hp_wwtp": [10.0],
        "capacity_hs": [20.1234],
        "power_hs": [3.4],
        "capacity_bs": [30.5678],
        "power_bs": [4.5],
        "hp_h": [4000.0, 6000.0],
        "hb_h": [2000.0, 2000.0],
        "chp_h": [1000.0, 3000.0],
        "eb_h": [500.0, 1500.0],
        "ieh_h": [2000.0, 2000.0],
        "bm_hb_h": [1000.0, 1000.0],
        "bm_chp_h": [400.0, 600.0],
        "wte_h": [1000.0, 1000.0],
        "geo_h": [500.0, 1500.0],
        "hp_river_h": [1000.0, 1000.0],
        "hp_wwtp_h": [500.0, 500.0],
        "hb_f": [2222.0, 2222.0],
        "chp_f": [3000.0, 3000.0],
        "bm_hb_f": [1100.0, 1300.0],
        "bm_chp_f": [200.0, 300.0],
        "hp_e": [1000.0, 2000.0],
        "hp_river_e": [300.0, 500.0],
        "hp_wwtp_e": [200.0, 300.0],
        "eb_e": [500.0, 1500.0],
        "z_D": [3000.0, 5000.0],
        "y_S_PV": [100.0, 200.0],
        "y_S_CHP": [200.0, 400.0],
        "y_S_BM_CHP": [50.0, 100.0],
    }
    return FakeModel(
        [FakeVariable(name, value) for name, series in values.items() for value in series]
    )


def test_solver_variables_are_converted_to_stable_portfolio(
    assert_json_characterization,
):
    result = extract_model_portfolio(_fake_model(), dt=0.5)
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "portfolio.json"
    expected = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert_json_characterization(result, expected)


def test_missing_optional_solver_variables_are_zero():
    model = FakeModel(
        [
            FakeVariable("power_heat_heat_pump", 0.0),
            FakeVariable("power_heat_boiler", 0.0),
            FakeVariable("power_chp", 0.0),
            FakeVariable("power_heat_chp", 0.0),
            FakeVariable("power_eb", 0.0),
            FakeVariable("power_ieh", 0.0),
            FakeVariable("capacity_hs", 0.0),
            FakeVariable("power_hs", 0.0),
            FakeVariable("capacity_bs", 0.0),
            FakeVariable("power_bs", 0.0),
        ]
    )

    result = extract_model_portfolio(model, dt=1.0)

    assert result["supply"] == {}
    assert result["storage"] == {}
    assert result["total_heat_production_mwh"] == 0.0
    assert result["elec_grid_kwh"] == 0.0
