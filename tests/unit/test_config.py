import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from dh_compass.config import ConfigurationError, load_config


def test_default_config_is_typed_and_resolves_paths(project_root):
    config = load_config(project_root=project_root)

    assert config.case == "bad_oeynhausen"
    assert isinstance(config.paths.project_root, Path)
    assert config.paths.project_root == project_root.resolve()
    assert config.paths.output_root == project_root.resolve() / "outputs"
    assert config.network.pipeline_cost_per_m == 1000.0
    assert config.optimization.highs_central_lp_method == "barrier"
    assert config.optimization.highs_decentral_lp_method == "barrier"
    assert config.optimization.reuse_models is True
    assert "citygml_function" in config.scenario.building_columns
    assert "citygml_fu" not in config.scenario.building_columns


def test_scenario_inherits_defaults(project_root):
    config = load_config(
        project_root=project_root,
        config_path=project_root / "configs" / "scenarios" / "bad_oeynhausen.toml",
    )

    assert config.scenario.case == "bad_oeynhausen"
    assert config.demand.slp_year == 2022
    assert config.paths.project_root == project_root.resolve()


def test_brilon_scenario_uses_its_own_case_name(project_root):
    config = load_config(
        project_root=project_root,
        config_path=project_root / "configs" / "scenarios" / "brilon.toml",
    )

    assert config.scenario.case == "brilon"


def test_resource_paths_follow_path_override(project_root, tmp_path):
    config_path = tmp_path / "paths.toml"
    config_path.write_text(
        "[paths]\nheat_supply_data = \"local-potential-data\"\n",
        encoding="utf-8",
    )

    config = load_config(project_root=project_root, config_path=config_path)

    assert config.resources.industrial_heat_path == (
        project_root / "local-potential-data" / "industrial_eh.gpkg"
    )


def _jsonable(value: Any):
    if isinstance(value, dict):
        def key_text(key):
            if isinstance(key, float) and key.is_integer():
                return str(int(key))
            return str(key)

        return {key_text(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def test_loaded_defaults_match_legacy_snapshot(project_root):
    """The TOML migration preserves the values used by the old Python defaults."""

    loaded = load_config(project_root=project_root)
    config = asdict(loaded)
    config.pop("paths")
    config["resources"] = {
        key: value
        for key, value in config["resources"].items()
        if not key.endswith("_path")
    }
    config["output"].pop("output_root")
    # Solver execution settings did not exist in the legacy defaults. Keep
    # comparing all original domain settings without changing the snapshot.
    for key in ("highs_central_lp_method", "highs_decentral_lp_method", "reuse_models"):
        config["optimization"].pop(key)

    expected_path = project_root / "tests" / "fixtures" / "legacy_default_values.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    assert _jsonable(config) == expected

    assert loaded.paths.building_data == (
        project_root / "data/external/Warmebedarf_NRW.gdb"
    )
    assert loaded.paths.heat_supply_data == (
        project_root / "data/external/heat_supply_potentials"
    )
    assert loaded.resources.industrial_heat_path == (
        project_root / "data/external/heat_supply_potentials/industrial_eh.gpkg"
    )
    assert loaded.resources.biomass_path == (
        project_root / "data/external/heat_supply_potentials/biomass_nuts2(1).gpkg"
    )
    assert loaded.resources.waste_to_energy_path == (
        project_root / "data/external/heat_supply_potentials/wte.gpkg"
    )
    assert loaded.resources.hydrothermal_path == (
        project_root / "data/external/heat_supply_potentials/hydrothermal_85_nrw.gpkg"
    )
    assert loaded.resources.rivers_lakes_path == (
        project_root / "data/external/heat_supply_potentials/rivers_lakes.gpkg"
    )
    assert loaded.resources.wwtp_path == (
        project_root / "data/external/heat_supply_potentials/wwtp.gpkg"
    )


@pytest.mark.parametrize(
    ("section", "value", "message"),
    [
        ("[demand]\ndt", "0", "demand.dt must be positive"),
        ("[optimization]\nsubgraph_order", '"not-an-order"', "optimization.subgraph_order"),
        ("[optimization]\nhighs_central_lp_method", '"unknown"', "highs_central_lp_method"),
        ("[optimization]\nreuse_models", '"yes"', "reuse_models must be a boolean"),
        (
            "[scenario]\nenabled_resources",
            '["unknown_resource"]',
            "unsupported value",
        ),
        ("[network]\nnot_a_key", "1", "Unknown configuration key"),
        (
            "[network.distribution_pipe_cost_coefficients]\ntypo",
            "1",
            "Unknown configuration key",
        ),
        (
            "[technologies.heat_storage_central.0]\nefficiency_charge",
            "-1",
            "efficiency_charge must be greater than 0 and at most 1",
        ),
    ],
)
def test_invalid_configuration_has_actionable_error(
    project_root, tmp_path, section, value, message
):
    config_path = tmp_path / "invalid.toml"
    config_path.write_text(f"{section} = {value}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match=message):
        load_config(project_root=project_root, config_path=config_path)
