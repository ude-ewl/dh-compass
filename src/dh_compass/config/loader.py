"""Load TOML configuration into typed :class:`AppConfig` objects."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from math import isfinite
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from .models import (
    AppConfig,
    DemandConfig,
    EconomicsConfig,
    NetworkConfig,
    OptimizationConfig,
    OutputConfig,
    PathConfig,
    ResourceConfig,
    ScenarioConfig,
    TechnologyConfig,
)

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]

_TECHNOLOGY_NAMES = (
    "pv_module",
    "roof_lengths",
    "roof_widths",
    "battery_storage",
    "chp",
    "boiler_decentral",
    "boiler_central",
    "heat_pump_decentral",
    "heat_pump_central",
    "heat_storage_decentral",
    "heat_storage_central",
    "electrode_boiler",
    "no_battery",
    "no_chp",
    "no_boiler",
    "no_heat_pump",
    "no_heat_storage",
    "no_electrode_boiler",
    "industrial_eh",
    "no_industrial_eh",
    "biomass_boiler",
    "no_biomass_boiler",
    "biomass_chp",
    "no_biomass_chp",
    "waste_to_energy",
    "no_waste_to_energy",
    "geothermal",
    "no_geothermal",
    "river_heat_pump",
    "no_river_heat_pump",
    "wwtp_heat_pump",
    "no_wwtp_heat_pump",
)

_COST_STRUCTURE_NAMES = (
    "chp",
    "hb_decentral",
    "hb_central",
    "bs",
    "hs_decentral",
    "hs_central",
    "eb",
    "hp_decentral",
    "hp_central",
    "ieh",
    "bm_hb",
    "bm_chp",
    "wte",
    "geo",
    "hp_river",
    "hp_wwtp",
)

_FIXED_COST_STRUCTURE_NAMES = (
    "chp",
    "hb_decentral",
    "hb_central",
    "bs",
    "hs",
    "eb",
    "hp_decentral",
    "hp_central",
    "ieh",
    "bm_hb",
    "bm_chp",
    "wte",
    "geo",
    "hp_river",
    "hp_wwtp",
)

_VARIABLE_COST_STRUCTURE_NAMES = (
    "chp",
    "hb_central",
    "ieh",
    "bm_hb",
    "bm_chp",
    "wte",
    "geo",
    "hp_river",
    "hp_wwtp",
)

_RESOURCE_NAMES = {
    "industrial_excess_heat",
    "biomass",
    "waste_to_energy",
    "geothermal",
    "river_heat_pump",
    "wwtp_heat_pump",
}
_SOURCE_NAMES = {"air", "ground", "groundwater", "river", "wwtp"}
_DECENTRAL_SOURCE_NAMES = {"air", "ground"}
_SINK_NAMES = {"radiator", "floor", "water", "dh_medium", "dh_low", "dh_high"}
_ROOF_TYPES = {"flat"}
_TECHNOLOGY_PARAMETER_NAMES = {
    "efficiency",
    "efficiency_charge",
    "efficiency_discharge",
    "efficiency_electric",
    "on_off",
    "energy_to_power",
    "lifetime",
    "reinvest_factor",
    "residual_value_factor",
    "dof_type",
    "power_to_heat_ratio",
}


class ConfigurationError(ValueError):
    """Raised when a TOML document does not satisfy the config contract."""


def _deep_merge(base: dict[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except OSError as exc:
        raise FileNotFoundError(f"Configuration file does not exist: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Invalid TOML in {path}: {exc}") from exc
    if not isinstance(document, dict):  # pragma: no cover - tomllib always returns a dict
        raise ConfigurationError(f"Configuration document must be an object: {path}")
    return document


def _numbered_dict(value: Mapping[Any, Any]) -> dict[int, dict[str, Any]]:
    return {int(key): copy.deepcopy(dict(item)) for key, item in value.items()}


def _cost_table(value: Mapping[Any, Any]) -> dict[float, float]:
    return {float(key): float(item) for key, item in value.items()}


def _default_document(default_path: Path | None = None) -> dict[str, Any]:
    """Load the canonical default document from ``configs/default.toml``."""

    return _read_toml(default_path or _PACKAGE_ROOT / "configs" / "default.toml")


def _path_for_project_root(value: Any, paths: PathConfig, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"resources.{field} must be a non-empty path string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        # Resource defaults are stored as filenames so a [paths] override of
        # heat_supply_data remains useful without duplicating the directory in
        # every resource entry.
        path = (
            paths.heat_supply_data / path
            if len(path.parts) == 1
            else paths.project_root / path
        )
    return path.resolve()


def _check_mapping(document: Mapping[str, Any], path: str) -> Mapping[str, Any]:
    value: Any = document
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise ConfigurationError(f"{path} must be a TOML table")
        value = value[part]
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{path} must be a TOML table")
    return value


def _check_keys(mapping: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(str(key) for key in mapping if key not in allowed)
    if unknown:
        names = ", ".join(unknown)
        raise ConfigurationError(f"Unknown configuration key(s) at {path}: {names}")


def _require_keys(mapping: Mapping[str, Any], required: Sequence[str], path: str) -> None:
    missing = [key for key in required if key not in mapping]
    if missing:
        names = ", ".join(missing)
        raise ConfigurationError(f"Missing required configuration key(s) at {path}: {names}")


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{path} must be a finite number")
    result = float(value)
    if not isfinite(result):
        raise ConfigurationError(f"{path} must be a finite number")
    return result


def _integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"{path} must be an integer")
    return value


def _non_empty_string(value: Any, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{path} must be a non-empty string")


def _nonnegative(value: Any, path: str) -> None:
    if _number(value, path) < 0:
        raise ConfigurationError(f"{path} must be nonnegative")


def _positive(value: Any, path: str) -> None:
    if _number(value, path) <= 0:
        raise ConfigurationError(f"{path} must be positive")


def _positive_fraction(value: Any, path: str) -> None:
    number = _number(value, path)
    if not 0 < number <= 1:
        raise ConfigurationError(f"{path} must be greater than 0 and at most 1")


def _validate_cost_table(value: Any, path: str) -> None:
    if not isinstance(value, Mapping) or not value:
        raise ConfigurationError(f"{path} must be a non-empty cost table")
    for key, amount in value.items():
        try:
            threshold = float(key)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"{path} keys must be numeric thresholds") from exc
        if not isfinite(threshold) or threshold <= 0:
            raise ConfigurationError(f"{path} keys must be positive finite numbers")
        _nonnegative(amount, f"{path}[{key!r}]")


def _validate_technology_table(value: Any, path: str) -> None:
    if not isinstance(value, Mapping) or not value:
        raise ConfigurationError(f"{path} must be a non-empty technology table")
    for key, parameters in value.items():
        try:
            int(key)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"{path} keys must be integer technology IDs") from exc
        if not isinstance(parameters, Mapping) or not parameters:
            raise ConfigurationError(f"{path}.{key} must be a non-empty table")
        _check_keys(parameters, _TECHNOLOGY_PARAMETER_NAMES, f"{path}.{key}")
        if "on_off" in parameters and parameters["on_off"] not in (0, 1):
            raise ConfigurationError(f"{path}.{key}.on_off must be 0 or 1")
        for name in (
            "efficiency",
            "energy_to_power",
            "lifetime",
            "power_to_heat_ratio",
        ):
            if name in parameters:
                _positive(parameters[name], f"{path}.{key}.{name}")
        for name in ("efficiency_charge", "efficiency_discharge", "efficiency_electric"):
            if name in parameters:
                _positive_fraction(parameters[name], f"{path}.{key}.{name}")
        if "dof_type" in parameters:
            if _integer(parameters["dof_type"], f"{path}.{key}.dof_type") < 0:
                raise ConfigurationError(f"{path}.{key}.dof_type must be nonnegative")
        for name in ("reinvest_factor", "residual_value_factor"):
            if name in parameters:
                _nonnegative(parameters[name], f"{path}.{key}.{name}")


def _validate_document(document: Mapping[str, Any]) -> None:
    """Validate the merged document before coercing it into dataclasses."""

    allowed_sections = {
        "scenario",
        "paths",
        "network",
        "demand",
        "optimization",
        "economics",
        "resources",
        "output",
        "technologies",
    }
    _check_keys(document, allowed_sections, "configuration")
    required_sections = allowed_sections - {"paths"}
    _require_keys(document, sorted(required_sections), "configuration")

    scenario = _check_mapping(document, "scenario")
    _check_keys(
        scenario,
        {
            "case",
            "geodata_frame",
            "bbox",
            "building_layer",
            "building_columns",
            "demand_aggregation",
            "enabled_resources",
        },
        "scenario",
    )
    _require_keys(
        scenario,
        [
            "case",
            "geodata_frame",
            "bbox",
            "building_layer",
            "building_columns",
            "demand_aggregation",
            "enabled_resources",
        ],
        "scenario",
    )
    for name in ("case", "geodata_frame", "building_layer", "demand_aggregation"):
        _non_empty_string(scenario[name], f"scenario.{name}")
    if scenario["geodata_frame"] not in {"bbox"}:
        raise ConfigurationError("scenario.geodata_frame must be one of: bbox")
    if scenario["demand_aggregation"] not in {"sum", "legacy_mean_lhd"}:
        raise ConfigurationError(
            "scenario.demand_aggregation must be one of: sum, legacy_mean_lhd"
        )
    bbox = scenario["bbox"]
    if isinstance(bbox, (str, bytes)) or not isinstance(bbox, Sequence) or len(bbox) != 4:
        raise ConfigurationError("scenario.bbox must contain west, south, east, and north")
    west, south, east, north = (_number(value, "scenario.bbox") for value in bbox)
    if west >= east or south >= north:
        raise ConfigurationError("scenario.bbox must have west < east and south < north")
    for name in ("building_columns", "enabled_resources"):
        values = scenario[name]
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
            raise ConfigurationError(f"scenario.{name} must be a non-empty list")
        for index, value in enumerate(values):
            _non_empty_string(value, f"scenario.{name}[{index}]")
    unsupported_resources = set(scenario["enabled_resources"]) - _RESOURCE_NAMES
    if unsupported_resources:
        names = ", ".join(sorted(unsupported_resources))
        raise ConfigurationError(f"scenario.enabled_resources contains unsupported value(s): {names}")

    paths = document.get("paths", {})
    if not isinstance(paths, Mapping):
        raise ConfigurationError("paths must be a TOML table")
    _check_keys(
        paths,
        {
            "data_root",
            "external_data",
            "reference_data",
            "examples_data",
            "cache_root",
            "templates_root",
            "output_root",
            "building_data",
            "heat_supply_data",
            "historical_timeseries",
            "slp_parameters",
            "temperature_grib",
            "cds_credentials",
            "viewer_template",
        },
        "paths",
    )
    for name, value in paths.items():
        _non_empty_string(value, f"paths.{name}")

    network = _check_mapping(document, "network")
    _check_keys(
        network,
        {
            "linear_heat_density_threshold",
            "flh",
            "pipeline_cost_per_m",
            "infrastructure_cost_factor",
            "pipeline_residual_interest_rate",
            "pipeline_residual_lifetime",
            "pipeline_residual_duration",
            "pipeline_residual_invest_cost_annual_change",
            "distribution_pipe_cost_coefficients",
            "building_connection_cost_coefficients",
            "transfer_station_cost_structure",
            "pump_cost_structure",
        },
        "network",
    )
    _require_keys(
        network,
        [
            "linear_heat_density_threshold",
            "flh",
            "pipeline_cost_per_m",
            "infrastructure_cost_factor",
            "pipeline_residual_interest_rate",
            "pipeline_residual_lifetime",
            "pipeline_residual_duration",
            "pipeline_residual_invest_cost_annual_change",
            "distribution_pipe_cost_coefficients",
            "building_connection_cost_coefficients",
            "transfer_station_cost_structure",
            "pump_cost_structure",
        ],
        "network",
    )
    _nonnegative(
        network["linear_heat_density_threshold"],
        "network.linear_heat_density_threshold",
    )
    _positive(network["flh"], "network.flh")
    for name in (
        "pipeline_cost_per_m",
        "infrastructure_cost_factor",
        "pipeline_residual_interest_rate",
    ):
        _nonnegative(network[name], f"network.{name}")
    for name in ("pipeline_residual_lifetime", "pipeline_residual_duration"):
        if _integer(network[name], f"network.{name}") <= 0:
            raise ConfigurationError(f"network.{name} must be positive")
    _positive(network["pipeline_residual_invest_cost_annual_change"], "network.pipeline_residual_invest_cost_annual_change")
    for name in ("distribution_pipe_cost_coefficients", "building_connection_cost_coefficients"):
        coefficients = network[name]
        if not isinstance(coefficients, Mapping):
            raise ConfigurationError(f"network.{name} must be a TOML table")
        _check_keys(coefficients, {"a", "b"}, f"network.{name}")
        _require_keys(coefficients, ["a", "b"], f"network.{name}")
        _nonnegative(coefficients["a"], f"network.{name}.a")
        _nonnegative(coefficients["b"], f"network.{name}.b")
    for name in ("transfer_station_cost_structure", "pump_cost_structure"):
        _validate_cost_table(network[name], f"network.{name}")

    demand = _check_mapping(document, "demand")
    demand_keys = {
        "slp_year",
        "slp_location",
        "slp_profile_type_subgraph",
        "slp_profile_type_building",
        "slp_temperature_zone",
        "source",
        "sink",
        "source_central",
        "sink_central",
        "carnot_eta",
        "dh_spread",
        "prices_fixed",
        "dt",
        "location",
        "observation_year",
        "tilt",
        "roof_type",
        "flat_roof_orientation",
    }
    _check_keys(demand, demand_keys, "demand")
    _require_keys(demand, sorted(demand_keys), "demand")
    for name in (
        "slp_location",
        "slp_profile_type_subgraph",
        "slp_profile_type_building",
        "slp_temperature_zone",
        "location",
        "roof_type",
    ):
        _non_empty_string(demand[name], f"demand.{name}")
    for name in ("slp_year", "observation_year"):
        if _integer(demand[name], f"demand.{name}") <= 0:
            raise ConfigurationError(f"demand.{name} must be positive")
    if demand["source"] not in _DECENTRAL_SOURCE_NAMES:
        raise ConfigurationError(
            "demand.source must be one of: "
            f"{', '.join(sorted(_DECENTRAL_SOURCE_NAMES))}"
        )
    if demand["source_central"] not in _SOURCE_NAMES:
        raise ConfigurationError(
            "demand.source_central must be one of: "
            f"{', '.join(sorted(_SOURCE_NAMES))}"
        )
    if demand["sink"] not in _SINK_NAMES or demand["sink_central"] not in _SINK_NAMES:
        raise ConfigurationError(
            f"demand.sink and demand.sink_central must be one of: {', '.join(sorted(_SINK_NAMES))}"
        )
    if demand["roof_type"] not in _ROOF_TYPES:
        raise ConfigurationError(
            f"demand.roof_type must be one of: {', '.join(sorted(_ROOF_TYPES))}"
        )
    if not isinstance(demand["prices_fixed"], bool):
        raise ConfigurationError("demand.prices_fixed must be a boolean")
    carnot_eta = _number(demand["carnot_eta"], "demand.carnot_eta")
    if not 0 < carnot_eta <= 1:
        raise ConfigurationError("demand.carnot_eta must be greater than 0 and at most 1")
    _nonnegative(demand["dh_spread"], "demand.dh_spread")
    _positive(demand["dt"], "demand.dt")
    tilt = _number(demand["tilt"], "demand.tilt")
    if not 0 <= tilt <= 90:
        raise ConfigurationError("demand.tilt must be between 0 and 90 degrees")
    orientation = _number(demand["flat_roof_orientation"], "demand.flat_roof_orientation")
    if not 0 <= orientation < 360:
        raise ConfigurationError("demand.flat_roof_orientation must be in [0, 360)")

    optimization = _check_mapping(document, "optimization")
    optimization_keys = {
        "max_workers",
        "subgraph_order",
        "n_clusters",
        "cluster_random_state",
        "decentral_heat_storage_intercept",
        "decentral_heat_storage_slope",
    }
    _check_keys(optimization, optimization_keys | {
        "highs_central_lp_method", "highs_decentral_lp_method", "reuse_models",
    }, "optimization")
    _require_keys(optimization, sorted(optimization_keys), "optimization")
    for name in ("highs_central_lp_method", "highs_decentral_lp_method"):
        value = optimization.get(name, "barrier")
        _non_empty_string(value, f"optimization.{name}")
        if value not in {"auto", "dual", "primal", "barrier", "ipx_dual"}:
            raise ConfigurationError(f"optimization.{name} must be one of: auto, dual, primal, barrier, ipx_dual")
    if not isinstance(optimization.get("reuse_models", True), bool):
        raise ConfigurationError("optimization.reuse_models must be a boolean")
    for name in ("max_workers", "n_clusters"):
        if _integer(optimization[name], f"optimization.{name}") <= 0:
            raise ConfigurationError(f"optimization.{name} must be positive")
    if optimization["subgraph_order"] not in {
        "demand_descending",
        "distance_ascending",
        "distance_greedy",
    }:
        raise ConfigurationError(
            "optimization.subgraph_order must be one of: "
            "demand_descending, distance_ascending, distance_greedy"
        )
    _integer(optimization["cluster_random_state"], "optimization.cluster_random_state")
    _nonnegative(
        optimization["decentral_heat_storage_intercept"],
        "optimization.decentral_heat_storage_intercept",
    )
    _nonnegative(
        optimization["decentral_heat_storage_slope"],
        "optimization.decentral_heat_storage_slope",
    )

    economics = _check_mapping(document, "economics")
    economics_scalar_keys = {
        "interest_rate",
        "investment_duration",
        "bos_factor",
        "fuel_price_central",
        "fuel_price_decentral",
        "electricity_price_central",
        "electricity_price_decentral",
        "price_sell_pv",
        "price_sell_chp",
        "fuel_price_biomass",
        "invest_cost_annual_change",
        "electricity_price_annual_change",
        "gas_price_annual_change",
        "pv_rem_annual_change",
        "chp_rem_annual_change",
        "cost_structures",
        "fixed_cost_structures",
        "variable_om_cost_structures",
    }
    _check_keys(economics, economics_scalar_keys, "economics")
    _require_keys(economics, sorted(economics_scalar_keys), "economics")
    for name in (
        "interest_rate",
        "bos_factor",
        "fuel_price_central",
        "fuel_price_decentral",
        "electricity_price_central",
        "electricity_price_decentral",
        "price_sell_pv",
        "price_sell_chp",
        "fuel_price_biomass",
    ):
        _nonnegative(economics[name], f"economics.{name}")
    if _integer(economics["investment_duration"], "economics.investment_duration") <= 0:
        raise ConfigurationError("economics.investment_duration must be positive")
    for name in (
        "invest_cost_annual_change",
        "electricity_price_annual_change",
        "gas_price_annual_change",
        "pv_rem_annual_change",
        "chp_rem_annual_change",
    ):
        _positive(economics[name], f"economics.{name}")
    for group, names in (
        ("cost_structures", _COST_STRUCTURE_NAMES),
        ("fixed_cost_structures", _FIXED_COST_STRUCTURE_NAMES),
        ("variable_om_cost_structures", _VARIABLE_COST_STRUCTURE_NAMES),
    ):
        tables = _check_mapping(document, f"economics.{group}")
        _check_keys(tables, set(names), f"economics.{group}")
        _require_keys(tables, names, f"economics.{group}")
        for name in names:
            _validate_cost_table(tables[name], f"economics.{group}.{name}")

    resources = _check_mapping(document, "resources")
    resource_keys = {
        "industrial_heat_path",
        "industrial_heat_scenario",
        "biomass_path",
        "biomass_scenario",
        "waste_to_energy_path",
        "waste_to_energy_scenario",
        "hydrothermal_path",
        "hydrothermal_scenario",
        "rivers_lakes_path",
        "wwtp_path",
    }
    _check_keys(resources, resource_keys, "resources")
    _require_keys(resources, sorted(resource_keys), "resources")
    for name, value in resources.items():
        _non_empty_string(value, f"resources.{name}")

    output = _check_mapping(document, "output")
    _check_keys(output, {"gif_fps"}, "output")
    _require_keys(output, ["gif_fps"], "output")
    _positive(output["gif_fps"], "output.gif_fps")

    technologies = _check_mapping(document, "technologies")
    _check_keys(technologies, set(_TECHNOLOGY_NAMES), "technologies")
    _require_keys(technologies, _TECHNOLOGY_NAMES, "technologies")
    pv_module = technologies["pv_module"]
    if not isinstance(pv_module, Mapping):
        raise ConfigurationError("technologies.pv_module must be a TOML table")
    _check_keys(
        pv_module,
        {"name", "dim_x", "dim_y", "c_inv", "power", "efficiency", "weight"},
        "technologies.pv_module",
    )
    _require_keys(
        pv_module,
        ["name", "dim_x", "dim_y", "c_inv", "power", "efficiency", "weight"],
        "technologies.pv_module",
    )
    _non_empty_string(pv_module["name"], "technologies.pv_module.name")
    for name in ("dim_x", "dim_y", "c_inv", "power", "weight"):
        _positive(pv_module[name], f"technologies.pv_module.{name}")
    efficiency = _number(pv_module["efficiency"], "technologies.pv_module.efficiency")
    if not 0 < efficiency <= 1:
        raise ConfigurationError("technologies.pv_module.efficiency must be in (0, 1]")
    roof_lengths = technologies["roof_lengths"]
    roof_widths = technologies["roof_widths"]
    for name, values in (("roof_lengths", roof_lengths), ("roof_widths", roof_widths)):
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
            raise ConfigurationError(f"technologies.{name} must be a non-empty list")
        for index, value in enumerate(values):
            _positive(value, f"technologies.{name}[{index}]")
    if len(roof_lengths) != len(roof_widths):
        raise ConfigurationError("technologies.roof_lengths and roof_widths must have matching lengths")
    for name in _TECHNOLOGY_NAMES:
        if name not in {"pv_module", "roof_lengths", "roof_widths"}:
            _validate_technology_table(technologies[name], f"technologies.{name}")


def _make_config(document: Mapping[str, Any], paths: PathConfig) -> AppConfig:
    scenario = document["scenario"]
    network = document["network"]
    demand = document["demand"]
    optimization = document["optimization"]
    economics = document["economics"]
    resources = document["resources"]
    technologies = document["technologies"]

    scenario_config = ScenarioConfig(
        case=str(scenario["case"]),
        geodata_frame=str(scenario["geodata_frame"]),
        bbox=tuple(float(v) for v in scenario["bbox"]),
        building_layer=str(scenario["building_layer"]),
        building_columns=tuple(str(v) for v in scenario["building_columns"]),
        demand_aggregation=str(scenario["demand_aggregation"]),
        enabled_resources=tuple(str(v) for v in scenario["enabled_resources"]),
    )
    network_config = NetworkConfig(
        linear_heat_density_threshold=float(network["linear_heat_density_threshold"]),
        flh=float(network["flh"]),
        pipeline_cost_per_m=float(network["pipeline_cost_per_m"]),
        infrastructure_cost_factor=float(network["infrastructure_cost_factor"]),
        pipeline_residual_interest_rate=float(network["pipeline_residual_interest_rate"]),
        pipeline_residual_lifetime=int(network["pipeline_residual_lifetime"]),
        pipeline_residual_duration=int(network["pipeline_residual_duration"]),
        pipeline_invest_cost_annual_change=float(network["pipeline_residual_invest_cost_annual_change"]),
        distribution_pipe_cost_coefficients={
            str(key): float(value)
            for key, value in network["distribution_pipe_cost_coefficients"].items()
        },
        building_connection_cost_coefficients={
            str(key): float(value)
            for key, value in network["building_connection_cost_coefficients"].items()
        },
        transfer_station_cost_structure=_cost_table(network["transfer_station_cost_structure"]),
        pump_cost_structure=_cost_table(network["pump_cost_structure"]),
    )
    demand_config = DemandConfig(
        slp_year=int(demand["slp_year"]),
        slp_location=str(demand["slp_location"]),
        slp_profile_type_subgraph=str(demand["slp_profile_type_subgraph"]),
        slp_profile_type_building=str(demand["slp_profile_type_building"]),
        slp_temperature_zone=str(demand["slp_temperature_zone"]),
        source=str(demand["source"]),
        sink=str(demand["sink"]),
        source_central=str(demand["source_central"]),
        sink_central=str(demand["sink_central"]),
        carnot_eta=float(demand["carnot_eta"]),
        dh_spread=float(demand["dh_spread"]),
        prices_fixed=bool(demand["prices_fixed"]),
        dt=float(demand["dt"]),
        location=str(demand["location"]),
        observation_year=int(demand["observation_year"]),
        tilt=float(demand["tilt"]),
        roof_type=str(demand["roof_type"]),
        flat_roof_orientation=float(demand["flat_roof_orientation"]),
    )
    optimization_config = OptimizationConfig(
        max_workers=int(optimization["max_workers"]),
        subgraph_order=str(optimization["subgraph_order"]),
        n_clusters=int(optimization["n_clusters"]),
        cluster_random_state=int(optimization["cluster_random_state"]),
        decentral_heat_storage_intercept=float(optimization["decentral_heat_storage_intercept"]),
        decentral_heat_storage_slope=float(optimization["decentral_heat_storage_slope"]),
        highs_central_lp_method=optimization.get("highs_central_lp_method", "barrier"),
        highs_decentral_lp_method=optimization.get("highs_decentral_lp_method", "barrier"),
        reuse_models=optimization.get("reuse_models", True),
    )
    economics_config = EconomicsConfig(
        interest_rate=float(economics["interest_rate"]),
        investment_duration=int(economics["investment_duration"]),
        bos_factor=float(economics["bos_factor"]),
        fuel_price_central=float(economics["fuel_price_central"]),
        fuel_price_decentral=float(economics["fuel_price_decentral"]),
        electricity_price_central=float(economics["electricity_price_central"]),
        electricity_price_decentral=float(economics["electricity_price_decentral"]),
        price_sell_pv=float(economics["price_sell_pv"]),
        price_sell_chp=float(economics["price_sell_chp"]),
        fuel_price_biomass=float(economics["fuel_price_biomass"]),
        invest_cost_annual_change=float(economics["invest_cost_annual_change"]),
        electricity_price_annual_change=float(economics["electricity_price_annual_change"]),
        gas_price_annual_change=float(economics["gas_price_annual_change"]),
        pv_rem_annual_change=float(economics["pv_rem_annual_change"]),
        chp_rem_annual_change=float(economics["chp_rem_annual_change"]),
        cost_structures={k: _cost_table(v) for k, v in economics["cost_structures"].items()},
        fixed_cost_structures={
            k: _cost_table(v) for k, v in economics["fixed_cost_structures"].items()
        },
        variable_om_cost_structures={
            k: _cost_table(v) for k, v in economics["variable_om_cost_structures"].items()
        },
    )
    technology_config = TechnologyConfig(
        pv_module=copy.deepcopy(technologies["pv_module"]),
        roof_lengths=tuple(float(v) for v in technologies["roof_lengths"]),
        roof_widths=tuple(float(v) for v in technologies["roof_widths"]),
        **{
            name: _numbered_dict(technologies[name])
            for name in _TECHNOLOGY_NAMES
            if name not in {"pv_module", "roof_lengths", "roof_widths"}
        },
    )
    resource_config = ResourceConfig(
        industrial_heat_path=_path_for_project_root(
            resources["industrial_heat_path"], paths, "industrial_heat_path"
        ),
        industrial_heat_scenario=str(resources["industrial_heat_scenario"]),
        biomass_path=_path_for_project_root(resources["biomass_path"], paths, "biomass_path"),
        biomass_scenario=str(resources["biomass_scenario"]),
        waste_to_energy_path=_path_for_project_root(
            resources["waste_to_energy_path"], paths, "waste_to_energy_path"
        ),
        waste_to_energy_scenario=str(resources["waste_to_energy_scenario"]),
        hydrothermal_path=_path_for_project_root(
            resources["hydrothermal_path"], paths, "hydrothermal_path"
        ),
        hydrothermal_scenario=str(resources["hydrothermal_scenario"]),
        rivers_lakes_path=_path_for_project_root(
            resources["rivers_lakes_path"], paths, "rivers_lakes_path"
        ),
        wwtp_path=_path_for_project_root(resources["wwtp_path"], paths, "wwtp_path"),
    )
    return AppConfig(
        scenario=scenario_config,
        paths=paths,
        network=network_config,
        demand=demand_config,
        optimization=optimization_config,
        economics=economics_config,
        technologies=technology_config,
        resources=resource_config,
        output=OutputConfig(output_root=paths.output_root, gif_fps=float(document["output"]["gif_fps"])),
    )


def _resolve_requested_path(
    config_path: str | Path | None, project_root: Path | None
) -> Path | None:
    if config_path is None:
        return None
    requested = Path(config_path).expanduser()
    if not requested.is_absolute():
        requested = (project_root / requested if project_root else Path.cwd() / requested)
    return requested.resolve()


def _infer_project_root(requested: Path | None) -> Path:
    if requested is not None:
        if requested.parent.name == "scenarios" and requested.parent.parent.name == "configs":
            return requested.parents[2]
        if requested.parent.name == "configs":
            return requested.parent.parent
    return _PACKAGE_ROOT


def _root_for_document(project_root: str | Path | None) -> Path:
    """Resolve the root used for an in-memory configuration document."""

    if project_root is not None:
        return Path(project_root).expanduser().resolve()
    return _PACKAGE_ROOT


def default_config_document(*, project_root: str | Path | None = None) -> dict[str, Any]:
    """Return a deep copy of the canonical default TOML document.

    The web application stores configuration documents in SQLite rather than
    storing an ``AppConfig`` object.  Keeping this small loader-level helper
    public lets that application boundary use exactly the same defaults as the
    CLI without importing private parsing details or duplicating the defaults.
    """

    root = _root_for_document(project_root)
    default_path = root / "configs" / "default.toml"
    if not default_path.exists() and root != _PACKAGE_ROOT:
        # A temporary web workspace may only contain its metadata database.  In
        # that case use the packaged defaults while still resolving configured
        # paths against the requested workspace root.
        default_path = _PACKAGE_ROOT / "configs" / "default.toml"
    return _default_document(default_path)


def merge_config_documents(
    document: Mapping[str, Any],
    *,
    base: Mapping[str, Any] | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Merge a partial document into defaults and validate the result.

    ``document`` is intentionally accepted as a mapping so API callers can
    submit JSON objects.  The returned object is detached from all inputs and
    is safe to persist as the immutable effective configuration of a revision.
    """

    if not isinstance(document, Mapping):
        raise ConfigurationError("Configuration document must be an object")
    defaults = dict(base) if base is not None else default_config_document(project_root=project_root)
    merged = _deep_merge(defaults, document)
    _validate_document(merged)
    return merged


def load_config_from_document(
    document: Mapping[str, Any],
    *,
    project_root: str | Path | None = None,
    inherit_defaults: bool = True,
) -> AppConfig:
    """Build an :class:`AppConfig` from an in-memory TOML/JSON document.

    This is the document counterpart to :func:`load_config`.  It is useful for
    persisted scenario revisions and deliberately shares the CLI validator and
    coercion path.  By default a partial scenario document inherits the
    canonical defaults; callers that already have an effective document may
    disable that merge.
    """

    root = _root_for_document(project_root)
    if inherit_defaults:
        effective = merge_config_documents(document, project_root=root)
    else:
        if not isinstance(document, Mapping):
            raise ConfigurationError("Configuration document must be an object")
        effective = copy.deepcopy(dict(document))
        _validate_document(effective)

    paths = PathConfig.from_project_root(root)
    path_values = effective.get("paths", {})
    if path_values:
        paths = paths.with_overrides(path_values)
    return _make_config(effective, paths)


def load_config(
    config_path: str | Path | None = None,
    *,
    project_root: str | Path | None = None,
) -> AppConfig:
    """Load the canonical defaults and merge an optional scenario TOML file.

    Relative paths in both documents are resolved from ``project_root`` (or the
    repository root inferred from a conventional ``configs/scenarios`` path),
    never from the caller's current working directory.
    """

    explicit_root = Path(project_root).expanduser().resolve() if project_root else None
    requested = _resolve_requested_path(config_path, explicit_root)
    root = explicit_root or _infer_project_root(requested)
    default_path = root / "configs" / "default.toml"
    document = _default_document(default_path)
    if requested is not None:
        if not requested.exists():
            raise FileNotFoundError(f"Configuration file does not exist: {requested}")
        if requested != default_path.resolve():
            document = _deep_merge(document, _read_toml(requested))

    return load_config_from_document(document, project_root=root, inherit_defaults=False)


def load_default_config(*, project_root: str | Path | None = None) -> AppConfig:
    """Convenience wrapper used by notebooks and the CLI."""

    return load_config(project_root=project_root)


__all__ = [
    "ConfigurationError",
    "default_config_document",
    "load_config",
    "load_config_from_document",
    "load_default_config",
    "merge_config_documents",
]
