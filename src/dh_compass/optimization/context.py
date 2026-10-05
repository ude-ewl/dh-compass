"""Explicit construction and validation of optimization runtime data."""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from math import isfinite
from typing import Callable

import pandas as pd

from dh_compass.config import (
    AppConfig,
    ResourceAvailability,
    TechnologyInputs,
    TimeSeriesData,
)
from dh_compass.demand.runtime import (
    build_building_profile_generator,
    build_technology_inputs,
)
from dh_compass.economics.cost_curves import residual_value_factor
from dh_compass.network.costs import build_network_cost_functions

from .model_inputs import (
    ContextDemandData,
    ContextMarketData,
    ContextTechnologyPortfolio,
    EconomicInputs,
    MarketTimeSeries,
    ModelInputs,
    ModelOptions,
    ResourceLimits,
    TechnologyPortfolio,
    build_model_inputs,
)
from .result_extraction import ModelSolution

CostFunction = Callable[[float], float]
ProfileGenerator = Callable[[float], pd.Series]


@dataclass(frozen=True)
class NetworkInputs:
    """Numeric network settings used during candidate evaluation."""

    pipeline_cost_per_m: float
    infrastructure_cost_factor: float
    residual_value_factor_pipeline: float


@dataclass(frozen=True)
class ClusteringOptions:
    """Settings for representative-building clustering."""

    n_clusters: int = 5
    random_state: int = 42


@dataclass(frozen=True)
class RuntimeServices:
    """Callables that are constructed at runtime and injected into a run.

    Keeping these services separate from numeric inputs makes the context
    serializable in principle and makes it obvious which values may perform
    work or access external data when called.
    """

    distribution_pipe_cost_func: CostFunction
    building_connection_cost_func: CostFunction
    pump_cost_func: CostFunction
    building_profile_generator: ProfileGenerator | None = None


@dataclass(frozen=True)
class OptimizationContext:
    """Validated runtime inputs for the optimization workflow.

    The context deliberately contains a small number of cohesive groups.  The
    model adapter selects central or decentralized values from these groups
    for each individual model build; candidate and cluster services use the
    network, clustering, and runtime-service groups directly.
    """

    economic: EconomicInputs
    market: ContextMarketData
    demand: ContextDemandData
    technologies: ContextTechnologyPortfolio
    resources: ResourceLimits
    options: ModelOptions
    network: NetworkInputs
    runtime_services: RuntimeServices
    clustering: ClusteringOptions

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate context dimensions and values before a solve starts.

        Model validation is reused for both modes so malformed technology
        dictionaries and profile lengths fail at context construction with a
        message that identifies the affected mode.
        """

        central_market = self.market.central
        decentral_market = self.market.decentral
        try:
            central_length = len(central_market.timestamps)
            decentral_length = len(decentral_market.timestamps)
        except TypeError as exc:
            raise ValueError(
                "Optimization context timestamps must be sized time series"
            ) from exc
        if central_length == 0 or decentral_length == 0:
            raise ValueError("Optimization context must contain at least one timestep")
        if central_length != decentral_length:
            raise ValueError(
                "Central and decentralized market profiles must have matching lengths "
                f"(central={central_length}, decentral={decentral_length})"
            )
        try:
            central_dt = float(central_market.dt)
            decentral_dt = float(decentral_market.dt)
        except (TypeError, ValueError) as exc:
            raise ValueError("market.dt must be a positive number") from exc
        if not isfinite(central_dt) or not isfinite(decentral_dt):
            raise ValueError("market.dt must be a finite positive number")
        if central_dt <= 0 or decentral_dt <= 0:
            raise ValueError("market.dt must be positive")
        if central_dt != decentral_dt:
            raise ValueError(
                "Central and decentralized market profiles must use the same dt"
            )

        try:
            n_clusters = int(self.clustering.n_clusters)
        except (TypeError, ValueError) as exc:
            raise ValueError("clustering.n_clusters must be a positive integer") from exc
        if n_clusters <= 0:
            raise ValueError("clustering.n_clusters must be positive")

        for name, value in (
            ("pipeline_cost_per_m", self.network.pipeline_cost_per_m),
            ("infrastructure_cost_factor", self.network.infrastructure_cost_factor),
        ):
            try:
                numeric_value = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"network.{name} must be a nonnegative number") from exc
            if not isfinite(numeric_value) or numeric_value < 0:
                raise ValueError(f"network.{name} must be nonnegative")
        try:
            pipeline_residual = float(self.network.residual_value_factor_pipeline)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "network.residual_value_factor_pipeline must be a finite number"
            ) from exc
        if not isfinite(pipeline_residual):
            raise ValueError(
                "network.residual_value_factor_pipeline must be a finite number"
            )

        for name, function in (
            ("distribution_pipe_cost_func", self.runtime_services.distribution_pipe_cost_func),
            ("building_connection_cost_func", self.runtime_services.building_connection_cost_func),
            ("pump_cost_func", self.runtime_services.pump_cost_func),
        ):
            if not callable(function):
                raise ValueError(f"runtime_services.{name} must be callable")
        if self.runtime_services.building_profile_generator is not None and not callable(
            self.runtime_services.building_profile_generator
        ):
            raise ValueError("runtime_services.building_profile_generator must be callable")

        for decentral, mode_name in ((False, "central"), (True, "decentralized")):
            try:
                model_inputs = build_model_inputs(
                    self,
                    [0.0] * central_length,
                    decentral=decentral,
                )
                model_inputs.validate()
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid {mode_name} optimization context inputs: {exc}"
                ) from exc

@dataclass
class OptimizationResult:
    """Result of evaluating one candidate area."""

    subgraph_id: int
    central_cost: float
    decentral_cost: float
    is_connected: bool
    connection_length: float
    grid_cost: float
    pump_cost: float = 0.0
    results_central: ModelSolution | None = None
    results_decentral: ModelSolution | None = None
    connecting_path_nodes: list[Hashable] | None = None


def build_optimization_context(
    config: AppConfig,
    time_series: TimeSeriesData,
    resources: ResourceAvailability | None = None,
    *,
    technology_inputs: TechnologyInputs | None = None,
    demand_electric_override: pd.Series | None = None,
    building_profile_generator: ProfileGenerator | None = None,
) -> OptimizationContext:
    """Build and validate a context from explicit configuration and inputs."""

    resources = resources or ResourceAvailability()
    inputs = technology_inputs or build_technology_inputs(config.paths, config, time_series)
    if building_profile_generator is None:
        building_profile_generator = build_building_profile_generator(
            config.paths, config, temperature_data=time_series.data
        )

    network_costs = build_network_cost_functions(
        distribution_coefficients=config.network.distribution_pipe_cost_coefficients,
        connection_coefficients=config.network.building_connection_cost_coefficients,
        transfer_station_structure=config.network.transfer_station_cost_structure,
        pump_structure=config.network.pump_cost_structure,
    )
    demand_electric = demand_electric_override
    if demand_electric is None:
        demand_electric = pd.Series(0.0, index=range(len(inputs.timestamps)))

    residual = config.network
    pipeline_residual = residual_value_factor(
        residual.pipeline_residual_interest_rate,
        residual.pipeline_residual_lifetime,
        residual.pipeline_residual_duration,
        residual.pipeline_invest_cost_annual_change,
    )

    economic = EconomicInputs(
        interest_rate=config.economics.interest_rate,
        investment_duration=config.economics.investment_duration,
        electricity_price_annual_change=inputs.electricity_price_annual_change,
        gas_price_annual_change=inputs.gas_price_annual_change,
        pv_rem_annual_change=inputs.pv_rem_annual_change,
        chp_rem_annual_change=inputs.chp_rem_annual_change,
        inv_cost=inputs.inv_cost,
        fixed_cost=inputs.fixed_cost,
        var_om_cost=inputs.var_om_cost,
    )

    market = ContextMarketData(
        central=MarketTimeSeries(
            dt=config.demand.dt,
            timestamps=inputs.timestamps,
            fuel_price=inputs.fuel_price_central,
            elec_price=inputs.elec_price_central,
            price_sell_pv=inputs.price_sell_pv,
            price_sell_chp=inputs.price_sell_chp,
            fuel_price_biomass=inputs.fuel_price_biomass,
        ),
        decentral=MarketTimeSeries(
            dt=config.demand.dt,
            timestamps=inputs.timestamps,
            fuel_price=inputs.fuel_price_decentral,
            elec_price=inputs.elec_price_decentral,
            price_sell_pv=inputs.price_sell_pv,
            price_sell_chp=inputs.price_sell_chp,
            fuel_price_biomass=inputs.fuel_price_biomass,
        ),
    )
    demand = ContextDemandData(
        demand_electric=demand_electric,
        pv_infeed=inputs.pv_infeed,
        solar_heat=inputs.solar_heat,
        cop_decentral=inputs.cop,
        cop_central=inputs.cop_central,
        cop_central_river=inputs.cop_central_river,
        cop_central_wwtp=inputs.cop_central_wwtp,
    )

    # A positive limit is the source of truth for location-dependent resource
    # activation.  This removes a duplicated availability flag from the
    # runtime context while preserving the old no-technology dictionaries.
    industrial_eh = (
        inputs.industrial_eh
        if resources.industrial_eh_energy_limit_mwh > 0
        else inputs.no_industrial_eh
    )
    biomass_boiler = (
        inputs.biomass_boiler
        if resources.biomass_energy_limit_mwh > 0
        else inputs.no_biomass_boiler
    )
    biomass_chp = (
        inputs.biomass_chp
        if resources.biomass_energy_limit_mwh > 0
        else inputs.no_biomass_chp
    )
    waste_to_energy = (
        inputs.waste_to_energy
        if resources.wte_energy_limit_mwh > 0
        else inputs.no_waste_to_energy
    )
    geothermal = (
        inputs.geothermal
        if resources.geothermal_energy_limit_mwh > 0
        else inputs.no_geothermal
    )
    river_heat_pump = (
        inputs.river_heat_pump
        if resources.river_hp_capacity_limit_kw > 0
        else inputs.no_river_heat_pump
    )
    wwtp_heat_pump = (
        inputs.wwtp_heat_pump
        if resources.wwtp_hp_capacity_limit_kw > 0
        else inputs.no_wwtp_heat_pump
    )

    central_technologies = TechnologyPortfolio(
        battery_storage=inputs.battery_storage,
        chp=inputs.chp,
        boiler=inputs.boiler_central,
        heat_pump=inputs.heat_pump_central,
        electrode_boiler=inputs.electrode_boiler,
        heat_storage=inputs.heat_storage_central,
        industrial_eh=industrial_eh,
        biomass_boiler=biomass_boiler,
        biomass_chp=biomass_chp,
        waste_to_energy=waste_to_energy,
        geothermal=geothermal,
        river_heat_pump=river_heat_pump,
        wwtp_heat_pump=wwtp_heat_pump,
    )
    decentral_technologies = TechnologyPortfolio(
        battery_storage=inputs.battery_storage,
        chp=inputs.chp_decentral,
        boiler=inputs.boiler_decentral,
        heat_pump=inputs.heat_pump_decentral,
        electrode_boiler=inputs.electrode_boiler,
        heat_storage=inputs.heat_storage_decentral,
        industrial_eh=industrial_eh,
        biomass_boiler=biomass_boiler,
        biomass_chp=biomass_chp,
        waste_to_energy=waste_to_energy,
        geothermal=geothermal,
        river_heat_pump=river_heat_pump,
        wwtp_heat_pump=wwtp_heat_pump,
    )

    context = OptimizationContext(
        economic=economic,
        market=market,
        demand=demand,
        technologies=ContextTechnologyPortfolio(
            central=central_technologies,
            decentral=decentral_technologies,
        ),
        resources=ResourceLimits(
            industrial_eh_energy_limit_mwh=resources.industrial_eh_energy_limit_mwh,
            biomass_energy_limit_mwh=resources.biomass_energy_limit_mwh,
            wte_energy_limit_mwh=resources.wte_energy_limit_mwh,
            geothermal_energy_limit_mwh=resources.geothermal_energy_limit_mwh,
            river_hp_capacity_limit_kw=resources.river_hp_capacity_limit_kw,
            wwtp_hp_capacity_limit_kw=resources.wwtp_hp_capacity_limit_kw,
        ),
        options=ModelOptions(
            ref_binary=0,
            decentral_bool=0,
            decentral_heat_storage_intercept=config.optimization.decentral_heat_storage_intercept,
            decentral_heat_storage_slope=config.optimization.decentral_heat_storage_slope,
        ),
        network=NetworkInputs(
            pipeline_cost_per_m=config.network.pipeline_cost_per_m,
            infrastructure_cost_factor=config.network.infrastructure_cost_factor,
            residual_value_factor_pipeline=pipeline_residual,
        ),
        runtime_services=RuntimeServices(
            distribution_pipe_cost_func=network_costs["distribution_pipe_cost_func"],
            building_connection_cost_func=network_costs["building_connection_cost_func"],
            pump_cost_func=network_costs["pump_cost_func"],
            building_profile_generator=building_profile_generator,
        ),
        clustering=ClusteringOptions(
            n_clusters=config.optimization.n_clusters,
            random_state=config.optimization.cluster_random_state,
        ),
    )
    return context



__all__ = [
    "ClusteringOptions",
    "ContextDemandData",
    "ContextMarketData",
    "ContextTechnologyPortfolio",
    "NetworkInputs",
    "ModelInputs",
    "OptimizationContext",
    "OptimizationResult",
    "RuntimeServices",
    "build_model_inputs",
    "build_optimization_context",
]
