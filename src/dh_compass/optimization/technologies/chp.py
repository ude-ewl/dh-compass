"""CHP and biomass-CHP constraints."""

from __future__ import annotations

from mip import Model

from ..model_inputs import ModelInputs
from ..variables import ModelVariables


def add_static_constraints(model: Model, inputs: ModelInputs, variables: ModelVariables) -> None:
    """Add fuel, heat-to-power, and availability relations for gas CHP."""

    definitions = inputs.technologies.chp
    chp = variables.chp
    for index in variables.indices.chp:
        definition = definitions[index]
        model += (
            chp.power_fuel_chp[index]
            == chp.power_chp[index] / definition["efficiency_electric"]
        )
        model += (
            chp.power_heat_chp[index]
            == chp.power_chp[index] * definition["power_to_heat_ratio"]
        )
        if definition["on_off"] == 0:
            model += chp.power_chp[index] == 0


def add_time_constraints(model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int) -> None:
    """Add dispatch limits and electricity export constraints for gas CHP."""

    definitions = inputs.technologies.chp
    chp = variables.chp
    for index in variables.indices.chp:
        definition = definitions[index]
        model += chp.chp_e[time_index][index] <= chp.power_chp[index]
        model += chp.chp_h[time_index][index] <= chp.power_heat_chp[index]
        model += (
            chp.chp_e[time_index][index] * definition["power_to_heat_ratio"]
            == chp.chp_h[time_index][index]
        )
        model += (
            chp.chp_f[time_index][index] * definition["efficiency_electric"]
            == chp.chp_e[time_index][index]
        )
        model += variables.flows.y_S_CHP[time_index] <= chp.chp_e[time_index][index]


def add_biomass_static_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Add sizing and availability relations for biomass CHP."""

    definitions = inputs.technologies.biomass_chp
    chp = variables.biomass_chp
    decentral = inputs.options.decentral_bool
    for index in variables.indices.biomass_chp:
        definition = definitions[index]
        model += (
            chp.power_fuel_bm_chp[index]
            == chp.power_bm_chp[index] / definition["efficiency_electric"]
        )
        model += (
            chp.power_heat_bm_chp[index]
            == chp.power_bm_chp[index] * definition["power_to_heat_ratio"]
        )
        if definition["on_off"] == 0 or decentral == 1:
            model += chp.power_bm_chp[index] == 0


def add_biomass_time_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int
) -> None:
    """Add dispatch limits and electricity export constraints for biomass CHP."""

    definitions = inputs.technologies.biomass_chp
    chp = variables.biomass_chp
    for index in variables.indices.biomass_chp:
        definition = definitions[index]
        model += chp.bm_chp_e[time_index][index] <= chp.power_bm_chp[index]
        model += chp.bm_chp_h[time_index][index] <= chp.power_heat_bm_chp[index]
        model += (
            chp.bm_chp_e[time_index][index] * definition["power_to_heat_ratio"]
            == chp.bm_chp_h[time_index][index]
        )
        model += (
            chp.bm_chp_f[time_index][index] * definition["efficiency_electric"]
            == chp.bm_chp_e[time_index][index]
        )
        model += (
            variables.flows.y_S_BM_CHP[time_index]
            <= chp.bm_chp_e[time_index][index]
        )


__all__ = [
    "add_biomass_static_constraints",
    "add_biomass_time_constraints",
    "add_static_constraints",
    "add_time_constraints",
]
