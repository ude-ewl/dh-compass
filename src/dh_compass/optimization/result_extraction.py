"""Convert solver output into solver-independent optimization results.

The optimization package is the boundary at which solver variables become domain
results.  Reporting consumes :class:`ModelSolution` instances (or their plain
portfolio representation) and does not need to know anything about the solver's
variable API.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from mip import Model


@dataclass(frozen=True)
class TechnologyResult:
    """Extracted result for a heat-producing technology."""

    capacity_kw: float = 0.0
    annual_energy_mwh: float = 0.0
    energy_share_pct: float = 0.0
    capacity_el_kw: float | None = None
    capacity_th_kw: float | None = None

    def to_dict(self) -> dict[str, float]:
        """Return the stable portfolio representation used by reporting."""

        if self.capacity_el_kw is not None or self.capacity_th_kw is not None:
            return {
                "capacity_el_kw": round(self.capacity_el_kw or 0.0, 4),
                "capacity_th_kw": round(self.capacity_th_kw or 0.0, 4),
                "annual_heat_energy_mwh": round(self.annual_energy_mwh, 4),
                "energy_share_pct": round(self.energy_share_pct, 2),
            }
        return {
            "capacity_kw": round(self.capacity_kw, 4),
            "annual_energy_mwh": round(self.annual_energy_mwh, 4),
            "energy_share_pct": round(self.energy_share_pct, 2),
        }


@dataclass(frozen=True)
class StorageResult:
    """Extracted capacity and power for a storage technology."""

    capacity_kwh: float = 0.0
    power_kw: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "capacity_kwh": round(self.capacity_kwh, 4),
            "power_kw": round(self.power_kw, 4),
        }


@dataclass(frozen=True)
class EnergyFlows:
    """Annualized energy flows extracted from one model solution."""

    heat_pump_kwh: float = 0.0
    boiler_kwh: float = 0.0
    chp_kwh: float = 0.0
    electrode_boiler_kwh: float = 0.0
    industrial_excess_heat_kwh: float = 0.0
    biomass_boiler_kwh: float = 0.0
    biomass_chp_kwh: float = 0.0
    waste_to_energy_kwh: float = 0.0
    geothermal_kwh: float = 0.0
    river_heat_pump_kwh: float = 0.0
    wwtp_heat_pump_kwh: float = 0.0
    fuel_boiler_kwh: float = 0.0
    fuel_chp_kwh: float = 0.0
    fuel_biomass_boiler_kwh: float = 0.0
    fuel_biomass_chp_kwh: float = 0.0
    electricity_heat_pump_kwh: float = 0.0
    electricity_river_heat_pump_kwh: float = 0.0
    electricity_wwtp_heat_pump_kwh: float = 0.0
    electricity_electrode_boiler_kwh: float = 0.0
    electricity_grid_kwh: float = 0.0
    pv_feed_in_kwh: float = 0.0
    chp_feed_in_kwh: float = 0.0
    biomass_chp_feed_in_kwh: float = 0.0

    @property
    def total_heat_production_kwh(self) -> float:
        return sum(
            (
                self.heat_pump_kwh,
                self.boiler_kwh,
                self.chp_kwh,
                self.electrode_boiler_kwh,
                self.industrial_excess_heat_kwh,
                self.biomass_boiler_kwh,
                self.biomass_chp_kwh,
                self.waste_to_energy_kwh,
                self.geothermal_kwh,
                self.river_heat_pump_kwh,
                self.wwtp_heat_pump_kwh,
            )
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "total_heat_production_mwh": round(
                self.total_heat_production_kwh / 1000, 4
            ),
            "fuel_boiler_kwh": round(self.fuel_boiler_kwh, 4),
            "fuel_chp_kwh": round(self.fuel_chp_kwh, 4),
            "fuel_biomass_boiler_kwh": round(self.fuel_biomass_boiler_kwh, 4),
            "fuel_biomass_chp_kwh": round(self.fuel_biomass_chp_kwh, 4),
            "elec_hp_kwh": round(self.electricity_heat_pump_kwh, 4),
            "elec_hp_river_kwh": round(
                self.electricity_river_heat_pump_kwh, 4
            ),
            "elec_hp_wwtp_kwh": round(
                self.electricity_wwtp_heat_pump_kwh, 4
            ),
            "elec_eb_kwh": round(self.electricity_electrode_boiler_kwh, 4),
            "elec_grid_kwh": round(self.electricity_grid_kwh, 4),
            "pv_feed_in_kwh": round(self.pv_feed_in_kwh, 4),
            "chp_feed_in_kwh": round(self.chp_feed_in_kwh, 4),
            "biomass_chp_feed_in_kwh": round(
                self.biomass_chp_feed_in_kwh, 4
            ),
        }


@dataclass(frozen=True)
class ModelSolution:
    """Solver-independent result of one central or decentralized model run.

    ``result_df`` and ``dimensions`` retain the time-series result needed by
    reporting and diagnostics.  They contain values only; no solver model or
    solver variables are retained.
    """

    supply: Mapping[str, TechnologyResult] = field(default_factory=dict)
    storage: Mapping[str, StorageResult] = field(default_factory=dict)
    energy_flows: EnergyFlows = field(default_factory=EnergyFlows)
    result_df: pd.DataFrame | None = None
    dimensions: Mapping[str, tuple[float, ...]] = field(default_factory=dict)
    objective_value: float | None = None

    def to_portfolio_dict(self) -> dict[str, object]:
        """Return the legacy, JSON-compatible portfolio shape."""

        portfolio = {
            "supply": {
                name: result.to_dict() for name, result in self.supply.items()
            },
            "storage": {
                name: result.to_dict() for name, result in self.storage.items()
            },
        }
        portfolio.update(self.energy_flows.to_dict())
        return portfolio


def _first(values: Mapping[str, Sequence[float]], name: str) -> float:
    entries = values.get(name, ())
    return float(entries[0]) if entries else 0.0


def _at(
    values: Mapping[str, Sequence[float]], name: str, index: int = 0
) -> float:
    entries = values.get(name, ())
    return float(entries[index]) if len(entries) > index else 0.0


def _sum_variable_values(
    values: Mapping[str, Sequence[float]], name: str, dt: float
) -> float:
    return float(sum(values.get(name, ())) * dt)


def _technology(
    capacity: float, energy_kwh: float, total_energy_kwh: float
) -> TechnologyResult:
    return TechnologyResult(
        capacity_kw=capacity,
        annual_energy_mwh=energy_kwh / 1000,
        energy_share_pct=(energy_kwh / total_energy_kwh * 100)
        if total_energy_kwh > 0
        else 0.0,
    )


def _cogeneration_technology(
    capacity_el: float,
    capacity_th: float,
    energy_kwh: float,
    total_energy_kwh: float,
) -> TechnologyResult:
    return TechnologyResult(
        annual_energy_mwh=energy_kwh / 1000,
        energy_share_pct=(energy_kwh / total_energy_kwh * 100)
        if total_energy_kwh > 0
        else 0.0,
        capacity_el_kw=capacity_el,
        capacity_th_kw=capacity_th,
    )


def _solution_from_values(
    values: Mapping[str, Sequence[float]],
    dt: float,
    *,
    result_df: pd.DataFrame | None = None,
    dimensions: Mapping[str, Sequence[float]] | None = None,
    objective_value: float | None = None,
) -> ModelSolution:
    """Build a typed solution from named variable series."""

    capacities = {
        "heat_pump": _first(values, "power_heat_heat_pump"),
        "boiler": _first(values, "power_heat_boiler"),
        "chp_el": _first(values, "power_chp"),
        "chp_th": _first(values, "power_heat_chp"),
        "electrode_boiler": _first(values, "power_eb"),
        "industrial_excess_heat": _first(values, "power_ieh"),
        "biomass_boiler": _first(values, "power_bm_hb"),
        "biomass_chp_el": _first(values, "power_bm_chp"),
        "biomass_chp_th": _first(values, "power_heat_bm_chp"),
        "waste_to_energy": _first(values, "power_wte"),
        "geothermal": _first(values, "power_geo"),
        "river_heat_pump": _first(values, "power_hp_river"),
        "wwtp_heat_pump": _first(values, "power_hp_wwtp"),
    }
    heat = {
        "heat_pump": _sum_variable_values(values, "hp_h", dt),
        "boiler": _sum_variable_values(values, "hb_h", dt),
        "chp": _sum_variable_values(values, "chp_h", dt),
        "electrode_boiler": _sum_variable_values(values, "eb_h", dt),
        "industrial_excess_heat": _sum_variable_values(values, "ieh_h", dt),
        "biomass_boiler": _sum_variable_values(values, "bm_hb_h", dt),
        "biomass_chp": _sum_variable_values(values, "bm_chp_h", dt),
        "waste_to_energy": _sum_variable_values(values, "wte_h", dt),
        "geothermal": _sum_variable_values(values, "geo_h", dt),
        "river_heat_pump": _sum_variable_values(values, "hp_river_h", dt),
        "wwtp_heat_pump": _sum_variable_values(values, "hp_wwtp_h", dt),
    }
    total = sum(heat.values())

    supply: dict[str, TechnologyResult] = {}
    simple_technologies = (
        "heat_pump",
        "boiler",
        "electrode_boiler",
        "industrial_excess_heat",
        "biomass_boiler",
        "waste_to_energy",
        "geothermal",
        "river_heat_pump",
        "wwtp_heat_pump",
    )
    capacity_names = {
        "heat_pump": "heat_pump",
        "boiler": "boiler",
        "electrode_boiler": "electrode_boiler",
        "industrial_excess_heat": "industrial_excess_heat",
        "biomass_boiler": "biomass_boiler",
        "waste_to_energy": "waste_to_energy",
        "geothermal": "geothermal",
        "river_heat_pump": "river_heat_pump",
        "wwtp_heat_pump": "wwtp_heat_pump",
    }
    for name in simple_technologies:
        if capacities[capacity_names[name]] > 1e-6 or heat[name] > 1e-6:
            supply[name] = _technology(capacities[capacity_names[name]], heat[name], total)

    if capacities["chp_el"] > 1e-6 or heat["chp"] > 1e-6:
        supply["chp"] = _cogeneration_technology(
            capacities["chp_el"], capacities["chp_th"], heat["chp"], total
        )
    if capacities["biomass_chp_el"] > 1e-6 or heat["biomass_chp"] > 1e-6:
        supply["biomass_chp"] = _cogeneration_technology(
            capacities["biomass_chp_el"],
            capacities["biomass_chp_th"],
            heat["biomass_chp"],
            total,
        )

    storage: dict[str, StorageResult] = {}
    if _first(values, "capacity_hs") > 1e-6:
        storage["heat_storage"] = StorageResult(
            capacity_kwh=_first(values, "capacity_hs"),
            power_kw=_first(values, "power_hs"),
        )
    if _first(values, "capacity_bs") > 1e-6:
        storage["battery_storage"] = StorageResult(
            capacity_kwh=_first(values, "capacity_bs"),
            power_kw=_first(values, "power_bs"),
        )

    flows = EnergyFlows(
        heat_pump_kwh=heat["heat_pump"],
        boiler_kwh=heat["boiler"],
        chp_kwh=heat["chp"],
        electrode_boiler_kwh=heat["electrode_boiler"],
        industrial_excess_heat_kwh=heat["industrial_excess_heat"],
        biomass_boiler_kwh=heat["biomass_boiler"],
        biomass_chp_kwh=heat["biomass_chp"],
        waste_to_energy_kwh=heat["waste_to_energy"],
        geothermal_kwh=heat["geothermal"],
        river_heat_pump_kwh=heat["river_heat_pump"],
        wwtp_heat_pump_kwh=heat["wwtp_heat_pump"],
        fuel_boiler_kwh=_sum_variable_values(values, "hb_f", dt),
        fuel_chp_kwh=_sum_variable_values(values, "chp_f", dt),
        fuel_biomass_boiler_kwh=_sum_variable_values(values, "bm_hb_f", dt),
        fuel_biomass_chp_kwh=_sum_variable_values(values, "bm_chp_f", dt),
        electricity_heat_pump_kwh=_sum_variable_values(values, "hp_e", dt),
        electricity_river_heat_pump_kwh=_sum_variable_values(
            values, "hp_river_e", dt
        ),
        electricity_wwtp_heat_pump_kwh=_sum_variable_values(
            values, "hp_wwtp_e", dt
        ),
        electricity_electrode_boiler_kwh=_sum_variable_values(values, "eb_e", dt),
        electricity_grid_kwh=_sum_variable_values(values, "z_D", dt),
        pv_feed_in_kwh=_sum_variable_values(values, "y_S_PV", dt),
        chp_feed_in_kwh=_sum_variable_values(values, "y_S_CHP", dt),
        biomass_chp_feed_in_kwh=_sum_variable_values(values, "y_S_BM_CHP", dt),
    )

    normalized_dimensions = {
        name: tuple(float(value) for value in entries)
        for name, entries in (dimensions or {}).items()
    }
    return ModelSolution(
        supply=supply,
        storage=storage,
        energy_flows=flows,
        result_df=result_df,
        dimensions=normalized_dimensions,
        objective_value=objective_value,
    )


def extract_model_solution(
    model: Model, dt: float, objective_value: float | None = None
) -> ModelSolution:
    """Extract a :class:`ModelSolution` from a solved solver model."""

    values: dict[str, list[float]] = {}
    for variable in model.vars:
        values.setdefault(variable.name, []).append(variable.x)
    return _solution_from_values(values, dt, objective_value=objective_value)


def model_solution_from_results(
    result_df: pd.DataFrame,
    results_dim: Mapping[str, Sequence[float]],
    dt: float,
    objective_value: float | None = None,
) -> ModelSolution:
    """Build a solution from the value-only output of ``gather_results_mip``."""

    values = {
        name: [float(value) for value in result_df[name].tolist()]
        for name in result_df.columns
        if name not in {
            "pv_infeed",
            "demand_electric",
            "demand_heat",
            "fuel_price",
            "price_sell_pv",
            "price_sell_chp",
            "elec_price",
        }
    }
    # Dimensioning values are authoritative for capacities.  Add them to the
    # same named-value map so this path produces exactly the same portfolio as
    # direct solver extraction.
    dimension_variables = {
        "power_hs": ("hs", 0),
        "capacity_hs": ("hs", 1),
        "power_bs": ("bs", 0),
        "capacity_bs": ("bs", 1),
        "power_heat_boiler": ("hb", 0),
        "power_eb": ("eb", 0),
        "power_chp": ("chp", 0),
        "power_heat_chp": ("chp", 1),
        "power_heat_heat_pump": ("hp", 0),
        "power_ieh": ("ieh", 0),
        "power_bm_hb": ("bm_hb", 0),
        "power_bm_chp": ("bm_chp", 0),
        "power_heat_bm_chp": ("bm_chp", 1),
        "power_wte": ("wte", 0),
        "power_geo": ("geo", 0),
        "power_hp_river": ("hp_river", 0),
        "power_hp_wwtp": ("hp_wwtp", 0),
    }
    for variable_name, (dimension_name, index) in dimension_variables.items():
        values[variable_name] = [_at(results_dim, dimension_name, index)]

    return _solution_from_values(
        values,
        dt,
        result_df=result_df,
        dimensions=results_dim,
        objective_value=objective_value,
    )


def extract_model_portfolio(model: Model, dt: float) -> dict[str, object]:
    """Return the stable portfolio dictionary for a solved model.

    This convenience function exposes the stable JSON-shaped presentation of
    a solution for callers that do not need the richer domain object.
    """

    return extract_model_solution(model, dt).to_portfolio_dict()


def gather_results_mip(
    model: Model,
    pv_infeed: Sequence[float],
    demand_electric: Sequence[float],
    demand_heat: Sequence[float],
    fuel_price: Sequence[float],
    elec_price: Sequence[float],
    price_sell_pv: Sequence[float],
    price_sell_chp: Sequence[float],
    dt: float,
) -> tuple[pd.DataFrame, dict[str, list[float]]]:
    """Gather solver variables and input profiles into a value-only table.

    Solver inspection stays at the optimization boundary; reporting consumes
    the resulting dataframe or :class:`ModelSolution` instead.
    """

    hours = int(len(pv_infeed) * dt)
    num_variables = len(model.vars) // hours

    var_names = [var.name for var in model.vars]
    var_values = [var.x for var in model.vars]
    var_column_names = [var_names[i * hours] for i in range(num_variables)]
    var_columns = np.array(
        [
            [var_values[j + i * hours] for i in range(num_variables)]
            for j in range(hours)
        ]
    )

    param_column_names = [
        "pv_infeed",
        "demand_electric",
        "demand_heat",
        "fuel_price",
        "price_sell_pv",
        "price_sell_chp",
        "elec_price",
    ]
    params_columns = np.transpose(
        [
            pv_infeed,
            demand_electric,
            demand_heat,
            fuel_price,
            price_sell_pv,
            price_sell_chp,
            elec_price,
        ]
    )
    vars_and_params = np.concatenate((var_columns, params_columns), axis=1)
    result_df = pd.DataFrame(
        vars_and_params, columns=var_column_names + param_column_names
    )

    results_dim = {
        "hs": [model.vars["power_hs"].x, model.vars["capacity_hs"].x],
        "bs": [model.vars["power_bs"].x, model.vars["capacity_bs"].x],
        "hb": [model.vars["power_heat_boiler"].x],
        "eb": [model.vars["power_eb"].x],
        "chp": [
            model.vars["power_chp"].x,
            model.vars["power_heat_chp"].x,
            model.vars["power_fuel_chp"].x,
        ],
        "hp": [model.vars["power_heat_heat_pump"].x],
        "ieh": [model.vars["power_ieh"].x],
        "bm_hb": [model.vars["power_bm_hb"].x],
        "bm_chp": [
            model.vars["power_bm_chp"].x,
            model.vars["power_heat_bm_chp"].x,
            model.vars["power_fuel_bm_chp"].x,
        ],
        "wte": [model.vars["power_wte"].x],
        "geo": [model.vars["power_geo"].x],
        "hp_river": [model.vars["power_hp_river"].x],
        "hp_wwtp": [model.vars["power_hp_wwtp"].x],
    }
    return result_df, results_dim

__all__ = [
    "EnergyFlows",
    "ModelSolution",
    "StorageResult",
    "TechnologyResult",
    "extract_model_portfolio",
    "extract_model_solution",
    "gather_results_mip",
    "model_solution_from_results",
]
