"""Typed inputs for the optimization model.

The mathematical model historically accepted every runtime value as a separate
keyword argument.  This module groups those values by responsibility while
leaving the technology dictionaries intentionally data-oriented.  The groups
are solver-independent and can therefore be constructed and tested without
creating a MIP model.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Callable, Mapping, Protocol, Sequence

import pandas as pd

NumericSeries = Sequence[float] | pd.Series
TimestampSeries = Sequence[object] | pd.Series
TechnologyValue = float | int | bool
TechnologyDefinition = Mapping[str, TechnologyValue]
TechnologyMap = Mapping[int, TechnologyDefinition]
CostFunction = Callable[[float], float]
CostValue = CostFunction | Mapping[str, CostFunction]
CostTable = Mapping[str, CostValue]


@dataclass(frozen=True)
class EconomicInputs:
    """Discounting, escalation, and technology cost functions."""

    interest_rate: float
    investment_duration: int
    electricity_price_annual_change: float
    gas_price_annual_change: float
    pv_rem_annual_change: float
    chp_rem_annual_change: float
    inv_cost: CostTable
    fixed_cost: CostTable
    var_om_cost: CostTable


@dataclass(frozen=True)
class MarketTimeSeries:
    """Market prices and remuneration sampled at the model time steps."""

    dt: float
    timestamps: TimestampSeries
    fuel_price: NumericSeries
    elec_price: NumericSeries
    price_sell_pv: NumericSeries
    price_sell_chp: NumericSeries
    fuel_price_biomass: NumericSeries


@dataclass(frozen=True)
class DemandTimeSeries:
    """Demand, renewable profiles, and heat-pump performance profiles."""

    demand_electric: NumericSeries
    demand_heat: NumericSeries
    pv_infeed: NumericSeries
    cop: NumericSeries
    solar_heat: NumericSeries
    cop_river_hp: NumericSeries
    cop_wwtp_hp: NumericSeries


@dataclass(frozen=True)
class TechnologyPortfolio:
    """Technology definitions available to one model run.

    The dictionaries retain the existing numeric technology indexes and
    parameter names.  They are deliberately not converted into a large family
    of technology-specific classes in this phase.
    """

    battery_storage: TechnologyMap
    chp: TechnologyMap
    boiler: TechnologyMap
    heat_pump: TechnologyMap
    electrode_boiler: TechnologyMap
    heat_storage: TechnologyMap
    industrial_eh: TechnologyMap
    biomass_boiler: TechnologyMap
    biomass_chp: TechnologyMap
    waste_to_energy: TechnologyMap
    geothermal: TechnologyMap
    river_heat_pump: TechnologyMap
    wwtp_heat_pump: TechnologyMap


@dataclass(frozen=True)
class ResourceLimits:
    """Energy and capacity limits for location-dependent technologies."""

    industrial_eh_energy_limit_mwh: float = 0.0
    biomass_energy_limit_mwh: float = 0.0
    wte_energy_limit_mwh: float = 0.0
    geothermal_energy_limit_mwh: float = 0.0
    river_hp_capacity_limit_kw: float = 0.0
    wwtp_hp_capacity_limit_kw: float = 0.0


@dataclass(frozen=True)
class ModelOptions:
    """Mode switches and sizing coefficients used by the model."""

    ref_binary: int | bool = 0
    decentral_bool: int | bool = 0
    decentral_heat_storage_intercept: float = 23.345
    decentral_heat_storage_slope: float = 0.617


@dataclass(frozen=True)
class ContextMarketData:
    """Market profiles shared by central and decentralized model runs.

    ``MarketTimeSeries`` describes one model run.  An optimization context
    needs both variants because the central and decentralized models use
    different fuel and electricity prices.  Keeping the variants together
    prevents callers from pairing prices from different runs accidentally.
    """

    central: MarketTimeSeries
    decentral: MarketTimeSeries

    def for_model(self, decentral: bool) -> MarketTimeSeries:
        """Return the market profiles for the requested model mode."""

        return self.decentral if decentral else self.central


@dataclass(frozen=True)
class ContextDemandData:
    """Demand and environmental profiles independent of a candidate load.

    Heat demand is supplied for each model invocation, so it intentionally is
    not stored here.  The remaining profiles are common runtime inputs with
    central/decentral COP variants.
    """

    demand_electric: NumericSeries
    pv_infeed: NumericSeries
    solar_heat: NumericSeries
    cop_decentral: NumericSeries
    cop_central: NumericSeries
    cop_central_river: NumericSeries
    cop_central_wwtp: NumericSeries

    def for_model(
        self,
        demand_heat: NumericSeries,
        *,
        decentral: bool,
    ) -> DemandTimeSeries:
        """Compose the model-ready demand group for one candidate run."""

        return DemandTimeSeries(
            demand_electric=self.demand_electric,
            demand_heat=demand_heat,
            pv_infeed=self.pv_infeed,
            cop=self.cop_decentral if decentral else self.cop_central,
            solar_heat=self.solar_heat,
            cop_river_hp=self.cop_central_river,
            cop_wwtp_hp=self.cop_central_wwtp,
        )


@dataclass(frozen=True)
class ContextTechnologyPortfolio:
    """Central and decentralized technology portfolios for one context."""

    central: TechnologyPortfolio
    decentral: TechnologyPortfolio

    def for_model(self, decentral: bool) -> TechnologyPortfolio:
        """Return the technology definitions for the requested model mode."""

        return self.decentral if decentral else self.central


class OptimizationContextLike(Protocol):
    """Grouped context contract consumed by the model-input adapter."""

    economic: EconomicInputs
    market: ContextMarketData
    demand: ContextDemandData
    technologies: ContextTechnologyPortfolio
    resources: ResourceLimits
    options: ModelOptions


@dataclass(frozen=True)
class ModelInputs:
    """Complete, typed input boundary for one model build."""

    economic: EconomicInputs
    market: MarketTimeSeries
    demand: DemandTimeSeries
    technologies: TechnologyPortfolio
    resources: ResourceLimits
    options: ModelOptions

    @classmethod
    def from_context(
        cls,
        context: OptimizationContextLike,
        demand_heat: NumericSeries,
        *,
        decentral: bool,
        ref_binary: int | bool = 0,
    ) -> "ModelInputs":
        """Build central or decentralized inputs from an optimization context."""

        return build_model_inputs(
            context,
            demand_heat,
            decentral=decentral,
            ref_binary=ref_binary,
        )

    def validate(self) -> None:
        """Validate dimensions and values required before model construction.

        The legacy model indexes every profile with the same time index and
        assumes technology dictionaries use zero-based contiguous indexes.  A
        validation error here is considerably easier to diagnose than an
        ``IndexError`` or a solver error later in model construction.
        """

        self._validate_time_series()
        self._validate_resources()
        self._validate_technologies()
        self._validate_options()
        self._validate_economics()

    def _validate_time_series(self) -> None:
        series = {
            "timestamps": self.market.timestamps,
            "fuel_price": self.market.fuel_price,
            "elec_price": self.market.elec_price,
            "price_sell_pv": self.market.price_sell_pv,
            "price_sell_chp": self.market.price_sell_chp,
            "fuel_price_biomass": self.market.fuel_price_biomass,
            "demand_electric": self.demand.demand_electric,
            "demand_heat": self.demand.demand_heat,
            "pv_infeed": self.demand.pv_infeed,
            "cop": self.demand.cop,
            "solar_heat": self.demand.solar_heat,
            "cop_river_hp": self.demand.cop_river_hp,
            "cop_wwtp_hp": self.demand.cop_wwtp_hp,
        }
        lengths: dict[str, int] = {}
        for name, values in series.items():
            try:
                length = len(values)
            except TypeError as exc:
                raise ValueError(f"Model time series '{name}' must have a length") from exc
            if length == 0:
                raise ValueError("Model time series must contain at least one timestep")
            lengths[name] = length

        expected_length = lengths["timestamps"]
        mismatches = {
            name: length
            for name, length in lengths.items()
            if length != expected_length
        }
        if mismatches:
            details = ", ".join(
                f"{name}={length}" for name, length in mismatches.items()
            )
            raise ValueError(
                "All model time series must have the same length as timestamps "
                f"({expected_length}); got {details}"
            )

        try:
            dt = float(self.market.dt)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"dt must be positive; got {self.market.dt!r}") from exc
        if not isfinite(dt) or dt <= 0:
            raise ValueError(f"dt must be positive; got {self.market.dt!r}")

    def _validate_resources(self) -> None:
        limits = self.resources
        for name, value in vars(limits).items():
            try:
                numeric_value = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Resource limit '{name}' must be nonnegative") from exc
            if not isfinite(numeric_value) or numeric_value < 0:
                raise ValueError(f"Resource limit '{name}' must be nonnegative")

    def _validate_technologies(self) -> None:
        required_fields = {
            "battery_storage": {
                "on_off",
                "energy_to_power",
                "efficiency_charge",
                "efficiency_discharge",
                "reinvest_factor",
                "residual_value_factor",
            },
            "chp": {
                "on_off",
                "power_to_heat_ratio",
                "efficiency_electric",
                "reinvest_factor",
                "residual_value_factor",
            },
            "boiler": {"on_off", "efficiency", "reinvest_factor", "residual_value_factor"},
            "heat_pump": {"on_off", "reinvest_factor", "residual_value_factor"},
            "electrode_boiler": {
                "on_off",
                "efficiency",
                "reinvest_factor",
                "residual_value_factor",
            },
            "heat_storage": {
                "on_off",
                "energy_to_power",
                "efficiency_charge",
                "efficiency_discharge",
                "reinvest_factor",
                "residual_value_factor",
            },
            "industrial_eh": {"on_off", "efficiency", "reinvest_factor", "residual_value_factor"},
            "biomass_boiler": {
                "on_off",
                "efficiency",
                "reinvest_factor",
                "residual_value_factor",
            },
            "biomass_chp": {
                "on_off",
                "power_to_heat_ratio",
                "efficiency_electric",
                "reinvest_factor",
                "residual_value_factor",
            },
            "waste_to_energy": {"on_off", "efficiency", "reinvest_factor", "residual_value_factor"},
            "geothermal": {"on_off", "efficiency", "reinvest_factor", "residual_value_factor"},
            "river_heat_pump": {"on_off", "reinvest_factor", "residual_value_factor"},
            "wwtp_heat_pump": {"on_off", "reinvest_factor", "residual_value_factor"},
        }

        for name, definitions in vars(self.technologies).items():
            if not definitions:
                raise ValueError(f"Technology '{name}' must define index 0")
            keys = set(definitions)
            if any(type(key) is not int or key < 0 for key in keys):
                raise ValueError(
                    f"Technology '{name}' must use nonnegative integer keys; "
                    f"got {list(keys)!r}"
                )
            expected_keys = set(range(len(keys)))
            if keys != expected_keys:
                raise ValueError(
                    f"Technology '{name}' must use zero-based contiguous keys; "
                    f"got {sorted(keys)!r}"
                )
            required = required_fields[name]
            for index, definition in definitions.items():
                missing = required.difference(definition)
                if missing:
                    missing_names = ", ".join(sorted(missing))
                    raise ValueError(
                        f"Technology '{name}' at index {index} is missing: {missing_names}"
                    )

    def _validate_options(self) -> None:
        for name in ("ref_binary", "decentral_bool"):
            value = getattr(self.options, name)
            if value not in (0, 1, False, True):
                raise ValueError(f"Model option '{name}' must be 0 or 1; got {value!r}")

    def _validate_economics(self) -> None:
        if self.economic.investment_duration <= 0:
            raise ValueError("investment_duration must be positive")
        if self.economic.interest_rate <= -1:
            raise ValueError("interest_rate must be greater than -1")


def build_model_inputs(
    context: OptimizationContextLike,
    demand_heat: NumericSeries,
    *,
    decentral: bool,
    ref_binary: int | bool = 0,
) -> ModelInputs:
    """Adapt an optimization context to one model run.

    Central and decentralized callers use this same adapter. The context selects
    a complete market, demand, and technology group together.
    """

    return ModelInputs(
        economic=context.economic,
        market=context.market.for_model(decentral),
        demand=context.demand.for_model(demand_heat, decentral=decentral),
        technologies=context.technologies.for_model(decentral),
        resources=context.resources,
        options=ModelOptions(
            ref_binary=ref_binary,
            decentral_bool=decentral,
            decentral_heat_storage_intercept=(
                context.options.decentral_heat_storage_intercept
            ),
            decentral_heat_storage_slope=context.options.decentral_heat_storage_slope,
        ),
    )


__all__ = [
    "ContextDemandData",
    "ContextMarketData",
    "ContextTechnologyPortfolio",
    "DemandTimeSeries",
    "EconomicInputs",
    "MarketTimeSeries",
    "ModelInputs",
    "ModelOptions",
    "OptimizationContextLike",
    "ResourceLimits",
    "TechnologyPortfolio",
    "build_model_inputs",
    "CostFunction",
    "CostTable",
    "CostValue",
    "NumericSeries",
    "TechnologyDefinition",
    "TechnologyMap",
    "TechnologyValue",
    "TimestampSeries",
]
