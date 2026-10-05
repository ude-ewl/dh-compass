"""Boiler-family conversion constraints."""

from __future__ import annotations

from mip import Model

from ..model_inputs import ModelInputs
from ..variables import ModelVariables


def add_static_constraints(model: Model, inputs: ModelInputs, variables: ModelVariables) -> None:
    """Add availability constraints for conventional gas boilers."""

    definitions = inputs.technologies.boiler
    boiler = variables.boiler
    for index in variables.indices.boiler:
        if definitions[index]["on_off"] == 0:
            model += boiler.power_heat_boiler[index] == 0


def add_time_constraints(model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int) -> None:
    """Link gas boiler heat output and fuel use to installed capacity."""

    dt = inputs.market.dt
    definitions = inputs.technologies.boiler
    boiler = variables.boiler
    for index in variables.indices.boiler:
        model += (
            boiler.hb_h[time_index][index]
            == boiler.hb_f[time_index][index] * definitions[index]["efficiency"]
        )
        model += (
            boiler.hb_h[time_index][index] * (1 / dt)
            <= boiler.power_heat_boiler[index]
        )


def add_electrode_static_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Add electrode-boiler availability and decentral sizing relations."""

    definitions = inputs.technologies.electrode_boiler
    electrode = variables.electrode_boiler
    for index in variables.indices.electrode_boiler:
        definition = definitions[index]
        if definition["on_off"] == 0:
            model += electrode.power_eb[index] == 0
        if inputs.options.decentral_bool == 1:
            # The legacy model uses the final air-heat-pump sizing variable for
            # every electrode boiler when constructing decentralized models.
            heat_pump_index = variables.indices.heat_pump[-1]
            model += (
                electrode.power_eb[index]
                == variables.heat_pump.power_heat_heat_pump[heat_pump_index]
            )


def add_electrode_time_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int
) -> None:
    """Link electrode-boiler electricity and heat dispatch."""

    dt = inputs.market.dt
    definitions = inputs.technologies.electrode_boiler
    electrode = variables.electrode_boiler
    for index in variables.indices.electrode_boiler:
        model += (
            electrode.eb_h[time_index][index]
            == electrode.eb_e[time_index][index] * definitions[index]["efficiency"]
        )
        model += (
            electrode.eb_h[time_index][index] * (1 / dt)
            <= electrode.power_eb[index]
        )


def add_biomass_static_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Add biomass-boiler availability constraints."""

    definitions = inputs.technologies.biomass_boiler
    boiler = variables.biomass_boiler
    for index in variables.indices.biomass_boiler:
        if definitions[index]["on_off"] == 0 or inputs.options.decentral_bool == 1:
            model += boiler.power_bm_hb[index] == 0


def add_biomass_time_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int
) -> None:
    """Link biomass-boiler heat output and fuel use to capacity."""

    dt = inputs.market.dt
    definitions = inputs.technologies.biomass_boiler
    boiler = variables.biomass_boiler
    for index in variables.indices.biomass_boiler:
        model += (
            boiler.bm_hb_h[time_index][index]
            == boiler.bm_hb_f[time_index][index]
            * definitions[index]["efficiency"]
        )
        model += (
            boiler.bm_hb_h[time_index][index] * (1 / dt)
            <= boiler.power_bm_hb[index]
        )


__all__ = [
    "add_biomass_static_constraints",
    "add_biomass_time_constraints",
    "add_electrode_static_constraints",
    "add_electrode_time_constraints",
    "add_static_constraints",
    "add_time_constraints",
]
