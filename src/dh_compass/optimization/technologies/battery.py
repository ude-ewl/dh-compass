"""Battery variable relations, dispatch limits, and state transitions."""

from __future__ import annotations

from mip import Model

from ..model_inputs import ModelInputs
from ..variables import ModelVariables


def add_static_constraints(model: Model, inputs: ModelInputs, variables: ModelVariables) -> None:
    """Add sizing and availability constraints for batteries."""

    definitions = inputs.technologies.battery_storage
    indices = variables.indices.battery
    battery = variables.battery
    for index in indices:
        definition = definitions[index]
        model += battery.capacity_bs[index] == (
            battery.power_bs[index] * definition["energy_to_power"]
        )
        if definition["on_off"] == 0:
            model += battery.power_bs[index] == 0


def add_time_constraints(model: Model, variables: ModelVariables, time_index: int) -> None:
    """Limit battery charging, discharging, and state of charge."""

    battery = variables.battery
    for index in variables.indices.battery:
        model += (
            battery.s_D[time_index][index] + battery.s_C[time_index][index]
            <= battery.power_bs[index]
        )
        model += battery.L_S[time_index][index] <= battery.capacity_bs[index]


def add_intermediate_state_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Connect consecutive battery state-of-charge values."""

    dt = inputs.market.dt
    definitions = inputs.technologies.battery_storage
    battery = variables.battery
    for time_index in variables.indices.reduced_time:
        for index in variables.indices.battery:
            definition = definitions[index]
            model += (
                battery.L_S[time_index + 1][index]
                == battery.L_S[time_index][index]
                + battery.s_C[time_index][index]
                * definition["efficiency_charge"]
                * dt
                - battery.s_D[time_index][index]
                / definition["efficiency_discharge"]
                * dt
            )


def add_terminal_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Close the battery cycle and force its initial state to zero."""

    dt = inputs.market.dt
    last_time = len(inputs.market.timestamps) - 1
    definitions = inputs.technologies.battery_storage
    battery = variables.battery
    for index in variables.indices.battery:
        definition = definitions[index]
        model += (
            battery.L_S[0][index]
            == battery.L_S[last_time][index]
            + battery.s_C[last_time][index]
            * definition["efficiency_charge"]
            * dt
            - battery.s_D[last_time][index]
            / definition["efficiency_discharge"]
            * dt
        )
        model += battery.L_S[0][index] == 0


__all__ = [
    "add_intermediate_state_constraints",
    "add_static_constraints",
    "add_terminal_constraints",
    "add_time_constraints",
]
