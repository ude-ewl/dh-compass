"""Air-source and source-specific heat-pump constraints."""

from __future__ import annotations

from mip import Model

from ..model_inputs import ModelInputs
from ..variables import ModelVariables


def add_static_constraints(model: Model, inputs: ModelInputs, variables: ModelVariables) -> None:
    """Add availability constraints for the regular heat pump."""

    definitions = inputs.technologies.heat_pump
    heat_pump = variables.heat_pump
    for index in variables.indices.heat_pump:
        if definitions[index]["on_off"] == 0:
            model += heat_pump.power_heat_heat_pump[index] == 0


def add_time_constraints(model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int) -> None:
    """Link regular heat-pump dispatch to COP and installed capacity."""

    cop = inputs.demand.cop
    heat_pump = variables.heat_pump
    for index in variables.indices.heat_pump:
        model += heat_pump.hp_h[time_index][index] <= heat_pump.power_heat_heat_pump[index]
        model += (
            heat_pump.hp_h[time_index][index]
            == cop[time_index] * heat_pump.hp_e[time_index][index]
        )


def add_river_time_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int
) -> None:
    """Link river heat-pump dispatch to its COP and installed capacity."""

    source = variables.river_heat_pump
    cop = inputs.demand.cop_river_hp
    for index in variables.indices.river_heat_pump:
        model += source.heat[time_index][index] <= source.power[index]
        model += (
            source.heat[time_index][index]
            == cop[time_index] * source.electricity[time_index][index]
        )


def add_wwtp_time_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int
) -> None:
    """Link WWTP heat-pump dispatch to its COP and installed capacity."""

    source = variables.wwtp_heat_pump
    cop = inputs.demand.cop_wwtp_hp
    for index in variables.indices.wwtp_heat_pump:
        model += source.heat[time_index][index] <= source.power[index]
        model += (
            source.heat[time_index][index]
            == cop[time_index] * source.electricity[time_index][index]
        )


__all__ = [
    "add_river_time_constraints",
    "add_static_constraints",
    "add_time_constraints",
    "add_wwtp_time_constraints",
]
