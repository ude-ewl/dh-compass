"""Constraints for location-dependent heat resources and resource limits."""

from __future__ import annotations

from mip import Model, xsum

from ..model_inputs import ModelInputs
from ..variables import ModelVariables


def add_industrial_excess_heat_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Gate industrial excess heat and apply its annual energy limit."""

    definitions = inputs.technologies.industrial_eh
    resource_limit = inputs.resources.industrial_eh_energy_limit_mwh
    decentral = inputs.options.decentral_bool
    resource = variables.industrial_excess_heat
    for index in variables.indices.industrial_eh:
        definition = definitions[index]
        if definition["on_off"] == 0 or decentral == 1:
            model += resource.power_ieh[index] == 0
        if decentral == 0 and definition["on_off"] == 1:
            if resource_limit > 0:
                model += (
                    xsum(
                        resource.ieh_h[time_index][index] * inputs.market.dt
                        for time_index in variables.indices.time
                    )
                    <= resource_limit * 1000
                )


def add_biomass_resource_limit(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Apply the shared annual biomass fuel limit to both biomass technologies."""

    resource_limit = inputs.resources.biomass_energy_limit_mwh
    if inputs.options.decentral_bool == 0 and resource_limit > 0:
        boiler = variables.biomass_boiler
        chp = variables.biomass_chp
        model += (
            xsum(
                boiler.bm_hb_f[time_index][index] * inputs.market.dt
                for time_index in variables.indices.time
                for index in variables.indices.biomass_boiler
            )
            + xsum(
                chp.bm_chp_f[time_index][index] * inputs.market.dt
                for time_index in variables.indices.time
                for index in variables.indices.biomass_chp
            )
            <= resource_limit * 1000
        )


def add_waste_to_energy_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Gate waste-to-energy and apply its annual heat limit."""

    definitions = inputs.technologies.waste_to_energy
    resource_limit = inputs.resources.wte_energy_limit_mwh
    decentral = inputs.options.decentral_bool
    resource = variables.waste_to_energy
    for index in variables.indices.waste_to_energy:
        definition = definitions[index]
        if definition["on_off"] == 0 or decentral == 1:
            model += resource.power_wte[index] == 0
        if decentral == 0 and definition["on_off"] == 1:
            if resource_limit > 0:
                model += (
                    xsum(
                        resource.wte_h[time_index][index] * inputs.market.dt
                        for time_index in variables.indices.time
                    )
                    <= resource_limit * 1000
                )


def add_geothermal_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Gate geothermal heat and apply its annual energy limit."""

    definitions = inputs.technologies.geothermal
    resource_limit = inputs.resources.geothermal_energy_limit_mwh
    decentral = inputs.options.decentral_bool
    resource = variables.geothermal
    for index in variables.indices.geothermal:
        definition = definitions[index]
        if definition["on_off"] == 0 or decentral == 1:
            model += resource.power_geo[index] == 0
        if decentral == 0 and definition["on_off"] == 1:
            if resource_limit > 0:
                model += (
                    xsum(
                        resource.geo_h[time_index][index] * inputs.market.dt
                        for time_index in variables.indices.time
                    )
                    <= resource_limit * 1000
                )


def add_river_capacity_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Gate river heat pumps and apply the central capacity limit."""

    definitions = inputs.technologies.river_heat_pump
    resource_limit = inputs.resources.river_hp_capacity_limit_kw
    decentral = inputs.options.decentral_bool
    source = variables.river_heat_pump
    for index in variables.indices.river_heat_pump:
        definition = definitions[index]
        if definition["on_off"] == 0 or decentral == 1:
            model += source.power[index] == 0
        if decentral == 0 and definition["on_off"] == 1:
            if resource_limit > 0:
                model += source.power[index] <= resource_limit


def add_wwtp_capacity_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Gate WWTP heat pumps and apply the central capacity limit."""

    definitions = inputs.technologies.wwtp_heat_pump
    resource_limit = inputs.resources.wwtp_hp_capacity_limit_kw
    decentral = inputs.options.decentral_bool
    source = variables.wwtp_heat_pump
    for index in variables.indices.wwtp_heat_pump:
        definition = definitions[index]
        if definition["on_off"] == 0 or decentral == 1:
            model += source.power[index] == 0
        if decentral == 0 and definition["on_off"] == 1:
            if resource_limit > 0:
                model += source.power[index] <= resource_limit


def add_industrial_time_constraint(
    model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int
) -> None:
    """Apply the dispatch-to-capacity limit for industrial excess heat."""

    dt = inputs.market.dt
    excess_heat = variables.industrial_excess_heat
    for index in variables.indices.industrial_eh:
        model += (
            excess_heat.ieh_h[time_index][index] * (1 / dt)
            <= excess_heat.power_ieh[index]
        )


def add_waste_to_energy_time_constraint(
    model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int
) -> None:
    """Apply the dispatch-to-capacity limit for waste-to-energy."""

    dt = inputs.market.dt
    waste = variables.waste_to_energy
    for index in variables.indices.waste_to_energy:
        model += (
            waste.wte_h[time_index][index] * (1 / dt)
            <= waste.power_wte[index]
        )


def add_geothermal_time_constraint(
    model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int
) -> None:
    """Apply the dispatch-to-capacity limit for geothermal heat."""

    dt = inputs.market.dt
    geothermal = variables.geothermal
    for index in variables.indices.geothermal:
        model += (
            geothermal.geo_h[time_index][index] * (1 / dt)
            <= geothermal.power_geo[index]
        )


def add_time_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int
) -> None:
    """Apply all local-resource dispatch-to-capacity limits."""

    add_industrial_time_constraint(model, inputs, variables, time_index)
    add_waste_to_energy_time_constraint(model, inputs, variables, time_index)
    add_geothermal_time_constraint(model, inputs, variables, time_index)


__all__ = [
    "add_biomass_resource_limit",
    "add_geothermal_constraints",
    "add_industrial_excess_heat_constraints",
    "add_industrial_time_constraint",
    "add_geothermal_time_constraint",
    "add_river_capacity_constraints",
    "add_time_constraints",
    "add_waste_to_energy_time_constraint",
    "add_waste_to_energy_constraints",
    "add_wwtp_capacity_constraints",
]
