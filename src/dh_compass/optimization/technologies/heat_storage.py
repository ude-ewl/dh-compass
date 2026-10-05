"""Heat-storage sizing, dispatch, and cyclic state constraints."""

from __future__ import annotations

from mip import Model

from ..model_inputs import ModelInputs
from ..variables import ModelVariables


def add_static_constraints(model: Model, inputs: ModelInputs, variables: ModelVariables) -> None:
    """Add heat-storage sizing, availability, and mode-specific relations."""

    definitions = inputs.technologies.heat_storage
    storage = variables.heat_storage
    for index in variables.indices.heat_storage:
        definition = definitions[index]
        if inputs.options.decentral_bool == 1:
            # Preserve the existing decentralized sizing relationship.  The
            # legacy loop used the final air heat-pump index here.
            heat_pump_index = variables.indices.heat_pump[-1]
            model += (
                storage.capacity_hs[index]
                == inputs.options.decentral_heat_storage_intercept
                + inputs.options.decentral_heat_storage_slope
                * variables.heat_pump.power_heat_heat_pump[heat_pump_index]
            )
        model += (
            storage.power_hs[index]
            == storage.capacity_hs[index] * (1 / definition["energy_to_power"])
        )
        if definition["on_off"] == 0:
            model += storage.power_hs[index] == 0


def add_time_constraints(model: Model, variables: ModelVariables, time_index: int) -> None:
    """Limit charging and discharging and cap the storage state."""

    storage = variables.heat_storage
    for index in variables.indices.heat_storage:
        model += (
            storage.hs_D[time_index][index] + storage.hs_C[time_index][index]
            <= storage.power_hs[index]
        )
        model += storage.hs_S[time_index][index] <= storage.capacity_hs[index]


def add_intermediate_state_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Connect consecutive heat-storage state values."""

    dt = inputs.market.dt
    definitions = inputs.technologies.heat_storage
    storage = variables.heat_storage
    for time_index in variables.indices.reduced_time:
        for index in variables.indices.heat_storage:
            definition = definitions[index]
            model += (
                storage.hs_S[time_index + 1][index]
                == storage.hs_S[time_index][index]
                + storage.hs_C[time_index][index]
                * definition["efficiency_charge"]
                * dt
                - storage.hs_D[time_index][index]
                / definition["efficiency_discharge"]
                * dt
            )


def add_terminal_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Close the heat-storage cycle and force its initial state to zero."""

    dt = inputs.market.dt
    last_time = len(inputs.market.timestamps) - 1
    definitions = inputs.technologies.heat_storage
    storage = variables.heat_storage
    for index in variables.indices.heat_storage:
        definition = definitions[index]
        model += (
            storage.hs_S[0][index]
            == storage.hs_S[last_time][index]
            + storage.hs_C[last_time][index]
            * definition["efficiency_charge"]
            * dt
            - storage.hs_D[last_time][index]
            / definition["efficiency_discharge"]
            * dt
        )
        model += storage.hs_S[0][index] == 0


__all__ = [
    "add_intermediate_state_constraints",
    "add_static_constraints",
    "add_terminal_constraints",
    "add_time_constraints",
]
