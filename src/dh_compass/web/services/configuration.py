"""Configuration translation at the web/application boundary.

The command line loader remains the source of truth for defaults and
validation.  This module only translates between transport/persistence
representations and that existing typed configuration contract; it does not
perform preprocessing or optimization work.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

from dh_compass.config import (
    ConfigurationError,
    PathConfig,
    default_config_document,
    load_config_from_document,
    merge_config_documents,
)

from ..schemas.base import FieldError


@dataclass(frozen=True, slots=True)
class ValidatedConfiguration:
    """An effective document and typed configuration produced by one validation."""

    document: dict[str, Any]
    config: Any
    changed_paths: tuple[str, ...]
    changed_from_default: tuple[str, ...]
    expert_override_count: int


@dataclass(frozen=True, slots=True)
class ConfigurationChange:
    """Downstream effect of changing one immutable configuration revision."""

    effect: str
    changed_paths: tuple[str, ...]
    preview_paths: tuple[str, ...]
    run_only_paths: tuple[str, ...]
    no_impact_paths: tuple[str, ...]
    preview_invalidated: bool
    new_run_required: bool
    reasons: tuple[str, ...]

    @property
    def run_only_change(self) -> bool:
        return self.new_run_required and not self.preview_invalidated

    def as_dict(self) -> dict[str, Any]:
        # Include both the descriptive effect and boolean flags.  The flags are
        # convenient for clients while ``effect`` is stable for presentation.
        return {
            "effect": self.effect,
            "changed_paths": list(self.changed_paths),
            "preview_paths": list(self.preview_paths),
            "run_only_paths": list(self.run_only_paths),
            "no_impact_paths": list(self.no_impact_paths),
            "preview_invalidated": self.preview_invalidated,
            "new_run_required": self.new_run_required,
            "run_only_change": self.run_only_change,
            "reasons": list(self.reasons),
        }


# These are intentionally UI metadata, not a second validation contract.  The
# loader remains authoritative for allowed values and numeric constraints.
_LABELS = {
    "scenario": "Scenario",
    "network": "Network and infrastructure",
    "demand": "Scenario and demand",
    "optimization": "Optimization and clustering",
    "economics": "Economics and prices",
    "technologies": "Technology assumptions",
    "resources": "Resource datasets and scenarios",
    "paths": "Paths and output",
    "linear_heat_density_threshold": "Linear heat density threshold",
    "geodata_frame": "Geodata selection",
    "enabled_resources": "Enabled resources",
    "max_workers": "Maximum workers",
    "n_clusters": "Number of clusters",
    "interest_rate": "Interest rate",
}

# The configuration document contains a few large maps.  A presentation group
# keeps those maps understandable without changing their canonical TOML paths.
_COST_CURVE_PREFIXES = (
    "economics.cost_structures.",
    "economics.fixed_cost_structures.",
    "economics.variable_om_cost_structures.",
    "network.transfer_station_cost_structure.",
    "network.pump_cost_structure.",
)

_CENTRAL_TECHNOLOGIES = {
    "chp",
    "boiler_central",
    "heat_pump_central",
    "heat_storage_central",
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
}

_PATH_FIELDS = {
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
}
_RUNTIME_FIELDS = {
    "paths.project_root",
    "output.output_root",
}

# Paths owned by the deployment are shown for transparency but cannot be
# changed from a scenario document.  Dataset/resource paths remain editable in
# a local workspace, while the API still validates the resulting configuration
# through the canonical loader.
_MANAGED_PATH_FIELDS = {
    "data_root",
    "external_data",
    "reference_data",
    "examples_data",
    "cache_root",
    "templates_root",
    "output_root",
    "viewer_template",
    "cds_credentials",
}

_UNITS = {
    "network.linear_heat_density_threshold": "MWh/(m·a)",
    "network.flh": "h/a",
    "network.pipeline_cost_per_m": "€/m",
    "network.pipeline_residual_interest_rate": "1/a",
    "demand.carnot_eta": "fraction",
    "demand.dh_spread": "K",
    "demand.dt": "h",
    "demand.tilt": "°",
    "demand.flat_roof_orientation": "°",
    "economics.interest_rate": "1/a",
    "economics.investment_duration": "a",
    "economics.bos_factor": "factor",
    "output.gif_fps": "frames/s",
}

# Impact classification follows the actual pipeline boundary rather than
# simply treating an entire configuration section as preprocessing.  A preview
# executes ``load_inputs`` and ``prepare_geospatial_data``; resource assessment,
# context construction, optimization, and report generation happen only in a
# complete run.
_STANDARD_KEYS = {
    "network.linear_heat_density_threshold",
}
_PREVIEW_PREFIXES = (
    "scenario.bbox",
    "scenario.geodata_frame",
    "scenario.building_layer",
    "scenario.building_columns",
    "scenario.demand_aggregation",
    "demand.slp_year",
    "demand.slp_location",
    "demand.slp_profile_type_subgraph",
    "demand.slp_temperature_zone",
    "paths.building_data",
    "paths.historical_timeseries",
    "paths.slp_parameters",
    "paths.temperature_grib",
)
_PREVIEW_KEYS = {
    "network.linear_heat_density_threshold",
    "network.flh",
    "network.distribution_pipe_cost_coefficients",
    "network.building_connection_cost_coefficients",
    "network.transfer_station_cost_structure",
    "network.pump_cost_structure",
}
_NO_DOWNSTREAM_KEYS = {
    "scenario.case",
    "output.gif_fps",
    "paths.templates_root",
    "paths.output_root",
    "paths.viewer_template",
    "paths.cds_credentials",
    "paths.project_root",
    "output.output_root",
}


def _path_policy(path: str) -> str | None:
    """Return the deployment policy for a path-valued configuration field."""

    if path in _RUNTIME_FIELDS:
        return "managed"
    section, _, leaf = path.partition(".")
    if section == "paths" and leaf in _PATH_FIELDS:
        return "managed" if leaf in _MANAGED_PATH_FIELDS else "workspace"
    if section == "resources" and leaf.endswith("_path"):
        return "resource"
    return None


def _group_for(path: str) -> tuple[str, str]:
    if any(path.startswith(prefix) for prefix in _COST_CURVE_PREFIXES):
        return "cost_curves", "Cost curves"
    section, _, remainder = path.partition(".")
    if section != "technologies":
        label = _LABELS.get(section, _humanize(section))
        return section, label
    technology = remainder.split(".", 1)[0]
    if technology in _CENTRAL_TECHNOLOGIES:
        return "central_technologies", "Central technologies"
    return "decentral_technologies", "Decentral technologies"


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _flatten(document: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in document.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping) and value:
            result.update(_flatten(value, path))
        else:
            result[path] = value
    return result


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _migrate_legacy_building_columns(document: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the historical NRW building-field typo in saved scenarios."""

    migrated = copy.deepcopy(dict(document))
    scenario = migrated.get("scenario")
    if not isinstance(scenario, Mapping):
        return migrated
    # The alias applies only to the bundled NRW layer. A custom source is
    # allowed to retain a genuinely named ``citygml_fu`` column.
    if scenario.get("building_layer") != "Raumwaermebedarf_ist":
        return migrated
    columns = scenario.get("building_columns")
    if not isinstance(columns, list) or "citygml_function" in columns:
        return migrated
    if "citygml_fu" not in columns:
        return migrated
    migrated["scenario"] = {
        **scenario,
        "building_columns": [
            "citygml_function" if column == "citygml_fu" else column
            for column in columns
        ],
    }
    return migrated


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _humanize(key: str) -> str:
    if key in _LABELS:
        return _LABELS[key]
    return key.replace("_", " ").replace(".", " / ").capitalize()


def _data_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "unknown"


def _field_constraints(path: str, value: Any) -> dict[str, Any]:
    constraints: dict[str, Any] = {}
    leaf = path.rsplit(".", 1)[-1]
    if path == "network.linear_heat_density_threshold":
        constraints["minimum"] = 0
    elif path in {
        "network.flh",
        "demand.dt",
        "output.gif_fps",
        "network.pipeline_residual_lifetime",
        "network.pipeline_residual_duration",
        "network.pipeline_residual_invest_cost_annual_change",
        "demand.slp_year",
        "demand.observation_year",
        "optimization.max_workers",
        "optimization.n_clusters",
        "economics.investment_duration",
        "economics.invest_cost_annual_change",
        "economics.electricity_price_annual_change",
        "economics.gas_price_annual_change",
        "economics.pv_rem_annual_change",
        "economics.chp_rem_annual_change",
    }:
        constraints["exclusive_minimum"] = 0
    elif path in {
        "network.pipeline_cost_per_m",
        "network.infrastructure_cost_factor",
        "network.pipeline_residual_interest_rate",
        "demand.dh_spread",
        "optimization.decentral_heat_storage_intercept",
        "optimization.decentral_heat_storage_slope",
        "economics.interest_rate",
        "economics.bos_factor",
        "economics.fuel_price_central",
        "economics.fuel_price_decentral",
        "economics.electricity_price_central",
        "economics.electricity_price_decentral",
        "economics.price_sell_pv",
        "economics.price_sell_chp",
        "economics.fuel_price_biomass",
        "technologies.pv_module.dim_x",
        "technologies.pv_module.dim_y",
        "technologies.pv_module.c_inv",
        "technologies.pv_module.power",
        "technologies.pv_module.weight",
    }:
        constraints["minimum"] = 0
    elif path in {"demand.carnot_eta"}:
        constraints.update({"exclusive_minimum": 0, "maximum": 1})
    elif path in {"demand.tilt"}:
        constraints.update({"minimum": 0, "maximum": 90})
    elif path in {"demand.flat_roof_orientation"}:
        constraints.update({"minimum": 0, "exclusive_maximum": 360})
    elif path == "scenario.bbox":
        constraints["min_items"] = 4
        constraints["max_items"] = 4
    elif path in {
        "scenario.building_columns",
        "scenario.enabled_resources",
        "technologies.roof_lengths",
        "technologies.roof_widths",
    }:
        constraints["min_items"] = 1

    # These constraints are useful to typed scalar editors as well as to
    # analysts reading the metadata.  The loader remains authoritative.
    if path.endswith(".on_off"):
        constraints["allowed_values"] = [0, 1]
    elif path.endswith(".dof_type"):
        constraints["minimum"] = 0
    elif leaf in {"lifetime", "energy_to_power", "power_to_heat_ratio"}:
        constraints["exclusive_minimum"] = 0
    elif leaf in {"reinvest_factor", "residual_value_factor"}:
        constraints["minimum"] = 0
    elif path.endswith(".a") or path.endswith(".b"):
        if path.startswith(
            (
                "network.distribution_pipe_cost_coefficients.",
                "network.building_connection_cost_coefficients.",
            )
        ):
            constraints["minimum"] = 0
    elif path == "technologies.pv_module.efficiency":
        constraints.update({"exclusive_minimum": 0, "maximum": 1})
    elif leaf in {"efficiency_charge", "efficiency_discharge", "efficiency_electric"}:
        constraints.update({"exclusive_minimum": 0, "maximum": 1})
    elif leaf == "efficiency":
        constraints["exclusive_minimum"] = 0
        if path == "technologies.pv_module.efficiency":
            constraints["maximum"] = 1
    elif path.startswith("resources.") or path.startswith("paths."):
        constraints["min_length"] = 1

    enum_values = {
        "scenario.geodata_frame": ["bbox"],
        "scenario.demand_aggregation": ["sum", "legacy_mean_lhd"],
        "demand.source": ["air", "ground"],
        "demand.source_central": ["air", "ground", "groundwater", "river", "wwtp"],
        "demand.sink": ["radiator", "floor", "water", "dh_medium", "dh_low", "dh_high"],
        "demand.sink_central": ["radiator", "floor", "water", "dh_medium", "dh_low", "dh_high"],
        "demand.roof_type": ["flat"],
        "optimization.subgraph_order": [
            "demand_descending",
            "distance_ascending",
            "distance_greedy",
        ],
    }
    if path in enum_values:
        constraints["allowed_values"] = enum_values[path]
    return constraints


def _impact_for(path: str) -> tuple[str, bool]:
    if path in _NO_DOWNSTREAM_KEYS:
        return "none", path not in _STANDARD_KEYS
    preview = (
        path in _PREVIEW_KEYS
        or any(path.startswith(key + ".") for key in _PREVIEW_KEYS)
        or any(path == prefix or path.startswith(prefix + ".") for prefix in _PREVIEW_PREFIXES)
    )
    # Enabled resource choices and all resource/technology/economic/optimizer
    # values are consumed after preprocessing and therefore require a new run,
    # not a new candidate preview.
    if preview:
        return "preview", path not in _STANDARD_KEYS
    return "run", path not in _STANDARD_KEYS


def _configuration_error_path(message: str) -> str:
    # Loader messages conventionally start with a dotted TOML path.  Unknown
    # key messages identify the table and key separately, so join them into a
    # control-addressable path for the Expert editor.
    unknown = re.search(
        r"Unknown configuration key\(s\) at\s+([A-Za-z_][\w.]*)\s*:\s*([^,]+)",
        message,
    )
    if unknown:
        return f"{unknown.group(1)}.{unknown.group(2).strip()}"
    at_match = re.search(r"\bat ([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)", message)
    if at_match:
        return at_match.group(1)
    match = re.match(r"([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*|\[[^]]+\])*)", message)
    return match.group(1) if match else "$"


def _toml_key(key: Any) -> str:
    text = str(key)
    if re.fullmatch(r"[A-Za-z0-9_-]+", text):
        return text
    return json.dumps(text, ensure_ascii=False)


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return f"{value:.1f}"
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_scalar(item) for item in value) + "]"
    raise TypeError(f"Unsupported TOML value: {type(value).__name__}")


def _toml_table(document: Mapping[str, Any], path: tuple[str, ...] = ()) -> list[str]:
    lines: list[str] = []
    if path:
        lines.append("[" + ".".join(_toml_key(part) for part in path) + "]")

    scalar_items = [
        (key, value)
        for key, value in document.items()
        if not isinstance(value, Mapping)
    ]
    for key, value in scalar_items:
        lines.append(f"{_toml_key(key)} = {_toml_scalar(value)}")

    child_items = [
        (str(key), value)
        for key, value in document.items()
        if isinstance(value, Mapping)
    ]
    for key, child in child_items:
        if lines:
            lines.append("")
        lines.extend(_toml_table(child, path + (key,)))
    return lines


class ConfigurationAdapter:
    """Translate persisted/API documents through the canonical config loader."""

    def __init__(self, project_root: str | Path | None = None):
        self.project_root = (
            Path(project_root).expanduser().resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[4]
        )
        self._defaults = default_config_document(project_root=self.project_root)

    @property
    def defaults(self) -> dict[str, Any]:
        return copy.deepcopy(self._defaults)

    def _validate_path_policy(
        self,
        document: Mapping[str, Any],
        *,
        base_document: Mapping[str, Any] | None = None,
    ) -> None:
        """Reject path overrides that escape the configured local workspace."""

        def within_project_root(value: str) -> bool:
            candidate = Path(value).expanduser()
            resolved = (
                candidate if candidate.is_absolute() else self.project_root / candidate
            ).resolve()
            return resolved.is_relative_to(self.project_root)

        base_paths = (
            base_document.get("paths", {})
            if isinstance(base_document, Mapping)
            else {}
        )
        paths = document.get("paths")
        if isinstance(paths, Mapping):
            for name, value in paths.items():
                path = f"paths.{name}"
                unchanged_managed_value = (
                    isinstance(base_paths, Mapping)
                    and name in base_paths
                    and base_paths[name] == value
                )
                if (
                    (name in _MANAGED_PATH_FIELDS or path in _RUNTIME_FIELDS)
                    and not unchanged_managed_value
                ):
                    raise ConfigurationError(
                        f"{path} is deployment-managed and cannot be changed in a scenario"
                    )
                if name in _PATH_FIELDS and isinstance(value, str):
                    if not within_project_root(value):
                        raise ConfigurationError(
                            f"{path} must be relative or inside the configured project root"
                        )

        resources = document.get("resources")
        if isinstance(resources, Mapping):
            for name, value in resources.items():
                if not str(name).endswith("_path") or not isinstance(value, str):
                    continue
                if not within_project_root(value):
                    raise ConfigurationError(
                        f"resources.{name} must be relative or inside the configured project root"
                    )

    def validate(
        self,
        document: Mapping[str, Any],
        *,
        base_document: Mapping[str, Any] | None = None,
        replace: bool = False,
    ) -> ValidatedConfiguration:
        """Validate a patch or complete configuration document.

        Patch semantics retain the existing CLI-compatible inheritance behavior.
        A full-document editor may request replacement semantics so removal of a
        dynamic map member is preserved instead of being restored by deep merge.
        """

        if not isinstance(document, Mapping):
            raise ConfigurationError("Configuration document must be an object")
        document = _migrate_legacy_building_columns(document)
        base = base_document if base_document is not None else self._defaults
        self._validate_path_policy(document, base_document=base)
        if replace:
            effective = copy.deepcopy(dict(document))
        else:
            effective = merge_config_documents(document, base=base, project_root=self.project_root)
        config = load_config_from_document(
            effective,
            project_root=self.project_root,
            inherit_defaults=False,
        )
        effective_flat = _flatten(effective)
        default_flat = _flatten(self._defaults)
        path_defaults = PathConfig.from_project_root(self.project_root)
        for field in _PATH_FIELDS:
            default_flat[f"paths.{field}"] = str(getattr(path_defaults, field))
        changed = tuple(
            sorted(
                path
                for path, value in effective_flat.items()
                if default_flat.get(path, object()) != value
            )
        )
        expert_count = sum(
            1 for path in changed if self.metadata_for_path(path).get("expert_only", True)
        )
        return ValidatedConfiguration(
            document=_jsonable(effective),
            config=config,
            changed_paths=changed,
            changed_from_default=changed,
            expert_override_count=expert_count,
        )

    def import_toml(
        self,
        content: str,
        *,
        base_document: Mapping[str, Any] | None = None,
    ) -> ValidatedConfiguration:
        if not isinstance(content, str) or not content.strip():
            raise ConfigurationError("TOML document must not be empty")
        try:
            document = tomllib.loads(content)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(f"Invalid TOML document: {exc}") from exc
        return self.validate(document, base_document=base_document)

    def export_toml(
        self,
        document: Mapping[str, Any],
        *,
        base_document: Mapping[str, Any] | None = None,
    ) -> str:
        validated = self.validate(
            document,
            base_document=self._defaults if base_document is None else base_document,
        )
        return "\n".join(_toml_table(validated.document)) + "\n"

    def merged_toml(
        self,
        document: Mapping[str, Any],
        *,
        base_document: Mapping[str, Any] | None = None,
    ) -> str:
        """Return the canonical, fully merged TOML representation.

        Raw TOML submissions are allowed to be partial.  This method is used
        for the review pane so the analyst can see exactly what would be
        applied, including inherited defaults, before saving a revision.
        """

        return self.export_toml(document, base_document=base_document)

    # Explicit aliases make the adapter convenient for import/export services
    # while keeping the descriptive method names used by the API routes.
    from_toml = import_toml
    to_toml = export_toml

    def json_document(self, document: Mapping[str, Any]) -> dict[str, Any]:
        """Return a detached JSON-safe document after canonical validation."""

        return self.validate(document).document

    def to_api_document(self, value: Any) -> dict[str, Any]:
        """Convert a TOML-shaped mapping or typed ``AppConfig`` to JSON data."""

        if isinstance(value, Mapping):
            return self.validate(value).document
        if not is_dataclass(value):
            raise TypeError("Configuration value must be a mapping or AppConfig dataclass")
        document = _jsonable(asdict(value))
        # These are runtime-only fields rather than TOML configuration keys.
        output = document.get("output")
        if isinstance(output, Mapping):
            document["output"] = {"gif_fps": output.get("gif_fps")}
        network = document.get("network")
        if isinstance(network, Mapping) and "pipeline_invest_cost_annual_change" in network:
            network = dict(network)
            network["pipeline_residual_invest_cost_annual_change"] = network.pop(
                "pipeline_invest_cost_annual_change"
            )
            document["network"] = network
        paths = document.get("paths")
        if isinstance(paths, Mapping):
            allowed_paths = {
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
            }
            path_document = {
                key: value
                for key, value in paths.items()
                if key in allowed_paths and key not in _MANAGED_PATH_FIELDS
            }
            defaults = PathConfig.from_project_root(self.project_root)
            path_document = {
                key: value
                for key, value in path_document.items()
                if str(value) != str(getattr(defaults, key))
            }
            if path_document:
                document["paths"] = path_document
            else:
                document.pop("paths", None)
        return self.validate(document).document

    def to_app_config(
        self,
        document: Mapping[str, Any],
        *,
        base_document: Mapping[str, Any] | None = None,
    ) -> Any:
        """Convert an API/TOML document to the validated typed ``AppConfig``."""

        validated = self.validate(document, base_document=base_document)
        return validated.config

    def metadata(
        self,
        *,
        document: Mapping[str, Any] | None = None,
        parent_document: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return metadata for every editable and visible configuration leaf.

        The returned list is deliberately generated from the canonical default
        document.  It therefore stays in lock-step with ``AppConfig`` as new
        scalar, cost-curve, or technology-map values are added, instead of
        relying on a manually maintained UI field registry.
        """

        effective = self.validate(document or self._defaults).document
        current = _flatten(effective)
        parent = _flatten(parent_document) if parent_document is not None else None
        defaults = _flatten(self._defaults)
        path_defaults = PathConfig.from_project_root(self.project_root)
        for field in _PATH_FIELDS:
            defaults[f"paths.{field}"] = str(getattr(path_defaults, field))
        defaults["paths.project_root"] = str(path_defaults.project_root)
        defaults["output.output_root"] = str(path_defaults.output_root)
        result: list[dict[str, Any]] = []
        # Cost curves and technology maps support user-defined keys. Include
        # their current leaves as well as defaults, otherwise a valid saved
        # override cannot be rendered, reset, or included in change summaries.
        for path in sorted(set(defaults) | set(current)):
            has_default = path in defaults
            default = defaults.get(path)
            value = current.get(path, default)
            parent_value = (
                parent.get(path, default) if parent is not None else default
            )
            result.append(
                self.metadata_for_path(
                    path,
                    default=default,
                    has_default=has_default,
                    value=value,
                    parent_value=parent_value,
                    changed_from_default=(not has_default or value != default),
                    changed_from_parent=(parent is not None and value != parent_value),
                )
            )
        return result

    def metadata_for_path(
        self,
        path: str,
        *,
        default: Any = None,
        has_default: bool | None = None,
        value: Any = None,
        parent_value: Any = None,
        changed_from_default: bool | None = None,
        changed_from_parent: bool = False,
    ) -> dict[str, Any]:
        default_flat = _flatten(self._defaults)
        if has_default is None:
            has_default = path in default_flat
        if default is None and has_default and path in default_flat:
            default = default_flat[path]
        if value is None and has_default and path in default_flat:
            value = default
        if parent_value is None:
            parent_value = default
        section = path.split(".", 1)[0]
        leaf = path.rsplit(".", 1)[-1]
        impact, expert_only = _impact_for(path)
        policy = _path_policy(path)
        sensitive = section in {"paths", "resources"} or leaf.endswith("_path")
        data_type = _data_type(value)
        if path == "network.linear_heat_density_threshold":
            data_type = "number"
        if changed_from_default is None:
            changed_from_default = value != default
        group, group_label = _group_for(path)
        return {
            "key": path,
            "section": section,
            "section_label": _LABELS.get(section, _humanize(section)),
            "group": group,
            "group_label": group_label,
            "label": _LABELS.get(leaf, _humanize(leaf)),
            "description": self._description_for(path),
            "data_type": data_type,
            "unit": _UNITS.get(path),
            "default": _jsonable(default),
            "has_default": has_default,
            "value": _jsonable(value),
            "parent_value": _jsonable(parent_value),
            "changed_from_default": bool(changed_from_default),
            "changed_from_parent": bool(changed_from_parent),
            "expert_only": expert_only,
            "editable": policy != "managed" and path not in _RUNTIME_FIELDS,
            "runtime_only": path in _RUNTIME_FIELDS,
            "impact": impact,
            "preprocessing_impact": impact == "preview",
            "sensitive": sensitive,
            "path_policy": policy,
            "constraints": _field_constraints(path, value),
        }

    def change(self, before: Mapping[str, Any], after: Mapping[str, Any]) -> ConfigurationChange:
        before_flat = _flatten(before)
        after_flat = _flatten(after)
        changed = tuple(
            sorted(
                path
                for path in set(before_flat) | set(after_flat)
                if before_flat.get(path, object()) != after_flat.get(path, object())
            )
        )
        preview_paths = tuple(
            path for path in changed if _impact_for(path)[0] == "preview"
        )
        run_only_paths = tuple(
            path for path in changed if _impact_for(path)[0] == "run"
        )
        no_impact_paths = tuple(
            path for path in changed if _impact_for(path)[0] == "none"
        )
        if not changed or (not preview_paths and not run_only_paths):
            effect = "no_downstream_impact"
        elif preview_paths:
            effect = "preview_invalidated"
        else:
            effect = "new_run_required"
        reasons = tuple(
            [f"{path} requires a new candidate preview" for path in preview_paths]
            + [f"{path} requires a new optimization run" for path in run_only_paths]
        )
        return ConfigurationChange(
            effect=effect,
            changed_paths=changed,
            preview_paths=preview_paths,
            run_only_paths=run_only_paths,
            no_impact_paths=no_impact_paths,
            preview_invalidated=bool(preview_paths),
            new_run_required=bool(preview_paths or run_only_paths),
            reasons=reasons,
        )

    @staticmethod
    def field_errors(exc: Exception) -> list[FieldError]:
        message = str(exc)
        return [FieldError(path=_configuration_error_path(message), message=message)]

    @staticmethod
    def canonical_json(document: Mapping[str, Any]) -> str:
        return _canonical(document)

    @staticmethod
    def deep_copy(document: Mapping[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(dict(document))

    @staticmethod
    def _description_for(path: str) -> str:
        descriptions = {
            "demand.slp_year": "Completed historical weather year for the selected study area.",
            "demand.slp_location": "Legacy CDS setting; automatic weather uses the selected area.",
            "paths.temperature_grib": "Legacy GRIB input; automatic weather is cached by area and year.",
            "paths.cds_credentials": "Legacy CDS credentials; Open-Meteo requires no user credentials.",
            "paths.historical_timeseries": "Reference demand-factor calendar; its temperatures are not used.",
            "network.linear_heat_density_threshold": (
                "Minimum annual heat demand per metre of network. Higher values "
                "usually produce fewer, denser candidate areas."
            ),
            "network.flh": "Full-load hours used to derive building peak heat load.",
            "demand.prices_fixed": "Use fixed electricity prices instead of loading market prices.",
            "optimization.max_workers": "Maximum parallel candidate evaluations for one run.",
            "optimization.n_clusters": "Number of representative building clusters.",
            "scenario.enabled_resources": "Resource types that may be assessed during a run.",
        }
        if path in descriptions:
            return descriptions[path]
        if path.startswith("scenario."):
            return "Scenario selection and study-area inputs."
        if path.startswith("demand."):
            return "Demand-profile, temperature, and heat-pump assumptions."
        if path.startswith("network."):
            return "Network screening, routing, and infrastructure cost assumption."
        if path.startswith("optimization."):
            return "Optimization ordering, clustering, and execution controls."
        if path.startswith("economics."):
            return "Prices, discounting, and technology cost curve assumption."
        if path.startswith("technologies."):
            return "Technology availability, efficiency, lifetime, and reinvestment assumption."
        if path.startswith("paths."):
            return "Filesystem location used by the configured deployment."
        if path.startswith("resources."):
            return "Location-dependent resource dataset or scenario selection."
        if path.startswith("output."):
            return "Generated-report output setting."
        return "Advanced model configuration value."


__all__ = [
    "ConfigurationAdapter",
    "ConfigurationChange",
    "ValidatedConfiguration",
]
