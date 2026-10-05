"""Typed, immutable configuration models for DH-COMPASS.

Configuration is deliberately represented as data.  The models in this module do
not read files or inspect the environment; use :func:`dh_compass.config.load_config`
to construct an :class:`AppConfig`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Mapping, Sequence

import pandas as pd

if TYPE_CHECKING:
    from dh_compass.optimization.context import OptimizationResult
    from dh_compass.optimization.orchestration import HeatGridOptimizer

TechnologyDefinition = Mapping[str, object]
TechnologyMap = Mapping[int, TechnologyDefinition]
CostTables = Mapping[str, object]


@dataclass(frozen=True)
class PathConfig:
    """All paths used by a run, resolved relative to the repository root."""

    project_root: Path
    data_root: Path
    external_data: Path
    reference_data: Path
    examples_data: Path
    cache_root: Path
    templates_root: Path
    output_root: Path
    building_data: Path
    heat_supply_data: Path
    historical_timeseries: Path
    slp_parameters: Path
    temperature_grib: Path
    cds_credentials: Path
    viewer_template: Path

    @classmethod
    def from_project_root(cls, project_root: str | Path | None = None) -> "PathConfig":
        if project_root is None:
            project_root = Path(__file__).resolve().parents[3]
        root = Path(project_root).expanduser().resolve()
        data = root / "data"
        reference = data / "reference"
        external = data / "external"
        templates = root / "templates"
        return cls(
            project_root=root,
            data_root=data,
            external_data=external,
            reference_data=reference,
            examples_data=data / "examples",
            cache_root=data / "cache",
            templates_root=templates,
            output_root=root / "outputs",
            building_data=external / "Warmebedarf_NRW.gdb",
            heat_supply_data=external / "heat_supply_potentials",
            historical_timeseries=reference / "sh_to_wh_ratio.csv",
            slp_parameters=reference / "slp_parameters.json",
            temperature_grib=data / "cache" / "download.grib",
            cds_credentials=reference / ".cdsapirc.txt",
            viewer_template=templates / "viewer.html",
        )

    def with_overrides(self, values: Mapping[str, str | Path]) -> "PathConfig":
        """Return a copy with paths from a TOML ``[paths]`` section applied."""

        updates: dict[str, Path] = {}
        for name, value in values.items():
            if not hasattr(self, name):
                raise ValueError(f"Unknown path configuration field: {name}")
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = self.project_root / path
            updates[name] = path.resolve()
        return PathConfig(**{**self.__dict__, **updates})


@dataclass(frozen=True)
class ScenarioConfig:
    """Choices that describe a geographic/scenario run."""

    case: str
    geodata_frame: str
    bbox: tuple[float, float, float, float]
    building_layer: str
    building_columns: tuple[str, ...]
    demand_aggregation: str
    enabled_resources: tuple[str, ...]


@dataclass(frozen=True)
class NetworkConfig:
    """Network screening and cost settings."""

    linear_heat_density_threshold: float
    flh: float
    pipeline_cost_per_m: float
    infrastructure_cost_factor: float
    pipeline_residual_interest_rate: float
    pipeline_residual_lifetime: int
    pipeline_residual_duration: int
    pipeline_invest_cost_annual_change: float
    distribution_pipe_cost_coefficients: Mapping[str, float]
    building_connection_cost_coefficients: Mapping[str, float]
    transfer_station_cost_structure: Mapping[float, float]
    pump_cost_structure: Mapping[float, float]


@dataclass(frozen=True)
class DemandConfig:
    """Demand profile and heat-pump calculation settings."""

    slp_year: int
    slp_location: str
    slp_profile_type_subgraph: str
    slp_profile_type_building: str
    slp_temperature_zone: str
    source: str
    sink: str
    source_central: str
    sink_central: str
    carnot_eta: float
    dh_spread: float
    prices_fixed: bool
    dt: float
    location: str
    observation_year: int
    tilt: float
    roof_type: str
    flat_roof_orientation: float


@dataclass(frozen=True)
class OptimizationConfig:
    """Optimization and clustering settings."""

    max_workers: int
    subgraph_order: str
    n_clusters: int
    cluster_random_state: int
    decentral_heat_storage_intercept: float
    decentral_heat_storage_slope: float
    highs_central_lp_method: str = "barrier"
    highs_decentral_lp_method: str = "barrier"
    reuse_models: bool = True


@dataclass(frozen=True)
class EconomicsConfig:
    """Prices, discounting, and stable technology cost tables."""

    interest_rate: float
    investment_duration: int
    bos_factor: float
    fuel_price_central: float
    fuel_price_decentral: float
    electricity_price_central: float
    electricity_price_decentral: float
    price_sell_pv: float
    price_sell_chp: float
    fuel_price_biomass: float
    invest_cost_annual_change: float
    electricity_price_annual_change: float
    gas_price_annual_change: float
    pv_rem_annual_change: float
    chp_rem_annual_change: float
    cost_structures: Mapping[str, Mapping[float, float]]
    fixed_cost_structures: Mapping[str, Mapping[float, float]]
    variable_om_cost_structures: Mapping[str, Mapping[float, float]]


@dataclass(frozen=True)
class TechnologyConfig:
    """Technology parameter dictionaries used to construct a runtime context."""

    pv_module: TechnologyDefinition
    roof_lengths: tuple[float, ...]
    roof_widths: tuple[float, ...]
    battery_storage: TechnologyMap
    chp: TechnologyMap
    boiler_decentral: TechnologyMap
    boiler_central: TechnologyMap
    heat_pump_decentral: TechnologyMap
    heat_pump_central: TechnologyMap
    heat_storage_decentral: TechnologyMap
    heat_storage_central: TechnologyMap
    electrode_boiler: TechnologyMap
    no_battery: TechnologyMap
    no_chp: TechnologyMap
    no_boiler: TechnologyMap
    no_heat_pump: TechnologyMap
    no_heat_storage: TechnologyMap
    no_electrode_boiler: TechnologyMap
    industrial_eh: TechnologyMap
    no_industrial_eh: TechnologyMap
    biomass_boiler: TechnologyMap
    no_biomass_boiler: TechnologyMap
    biomass_chp: TechnologyMap
    no_biomass_chp: TechnologyMap
    waste_to_energy: TechnologyMap
    no_waste_to_energy: TechnologyMap
    geothermal: TechnologyMap
    no_geothermal: TechnologyMap
    river_heat_pump: TechnologyMap
    no_river_heat_pump: TechnologyMap
    wwtp_heat_pump: TechnologyMap
    no_wwtp_heat_pump: TechnologyMap


@dataclass(frozen=True)
class ResourceConfig:
    """External heat-potential datasets and their scenario columns."""

    industrial_heat_path: Path
    industrial_heat_scenario: str
    biomass_path: Path
    biomass_scenario: str
    waste_to_energy_path: Path
    waste_to_energy_scenario: str
    hydrothermal_path: Path
    hydrothermal_scenario: str
    rivers_lakes_path: Path
    wwtp_path: Path


@dataclass(frozen=True)
class OutputConfig:
    """Generated artifact settings."""

    output_root: Path
    gif_fps: float


@dataclass(frozen=True)
class AppConfig:
    """Complete configuration passed explicitly through the application."""

    scenario: ScenarioConfig
    paths: PathConfig
    network: NetworkConfig
    demand: DemandConfig
    optimization: OptimizationConfig
    economics: EconomicsConfig
    technologies: TechnologyConfig
    resources: ResourceConfig
    output: OutputConfig

    @property
    def case(self) -> str:
        """Convenience access for loggers and output naming."""

        return self.scenario.case


@dataclass(frozen=True)
class ResourceAvailability:
    """Result of checking location-dependent heat resources."""

    industrial_eh_available: bool = False
    industrial_eh_energy_limit_mwh: float = 0.0
    biomass_available: bool = False
    biomass_energy_limit_mwh: float = 0.0
    wte_available: bool = False
    wte_energy_limit_mwh: float = 0.0
    geothermal_available: bool = False
    geothermal_energy_limit_mwh: float = 0.0
    river_hp_available: bool = False
    river_hp_capacity_limit_kw: float = 0.0
    wwtp_hp_available: bool = False
    wwtp_hp_capacity_limit_kw: float = 0.0


@dataclass(frozen=True)
class TimeSeriesData:
    """Input time series loaded for a run."""

    data: pd.DataFrame
    timestamps: pd.Series
    length: int
    days: float


@dataclass(frozen=True)
class TechnologyInputs:
    """Runtime arrays and cost functions derived from explicit configuration."""

    timestamps: pd.Series
    fuel_price_central: list[float]
    fuel_price_decentral: list[float]
    elec_price_central: list[float]
    elec_price_decentral: list[float]
    price_sell_pv: list[float]
    price_sell_chp: list[float]
    fuel_price_biomass: list[float]
    electricity_price_annual_change: float
    gas_price_annual_change: float
    pv_rem_annual_change: float
    chp_rem_annual_change: float
    pv_infeed: list[float]
    cop: list[float]
    cop_central: list[float]
    cop_central_river: list[float]
    cop_central_wwtp: list[float]
    solar_heat: list[float]
    battery_storage: TechnologyMap
    chp: TechnologyMap
    chp_decentral: TechnologyMap
    boiler_central: TechnologyMap
    boiler_decentral: TechnologyMap
    heat_pump_central: TechnologyMap
    heat_pump_decentral: TechnologyMap
    electrode_boiler: TechnologyMap
    heat_storage_central: TechnologyMap
    heat_storage_decentral: TechnologyMap
    industrial_eh: TechnologyMap
    no_industrial_eh: TechnologyMap
    biomass_boiler: TechnologyMap
    no_biomass_boiler: TechnologyMap
    biomass_chp: TechnologyMap
    no_biomass_chp: TechnologyMap
    waste_to_energy: TechnologyMap
    no_waste_to_energy: TechnologyMap
    geothermal: TechnologyMap
    no_geothermal: TechnologyMap
    river_heat_pump: TechnologyMap
    no_river_heat_pump: TechnologyMap
    wwtp_heat_pump: TechnologyMap
    no_wwtp_heat_pump: TechnologyMap
    inv_cost: CostTables
    fixed_cost: CostTables
    var_om_cost: CostTables


@dataclass(frozen=True)
class PreparedGeospatialData:
    """Inputs prepared for optimization.

    Geospatial objects intentionally remain opaque at this application boundary;
    their concrete types are supplied by GeoPandas and NetworkX adapters.
    """

    buildings: object
    street_network: object
    lhd_graph: object
    subgraph_dict: Mapping[int, object]
    subgraph_attributes_df: object


@dataclass(frozen=True)
class RunArtifacts:
    """Outputs and intermediate data produced by :func:`run_pipeline`."""

    config: AppConfig
    prepared: PreparedGeospatialData
    resources: ResourceAvailability
    optimizer: HeatGridOptimizer
    optimization_results: Sequence[OptimizationResult]
    output_dir: Path
    full_results: Mapping[str, object] | None = None
    viewer_data: Mapping[str, object] | None = None
