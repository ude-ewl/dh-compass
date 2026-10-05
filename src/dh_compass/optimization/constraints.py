"""Shared model balances and composition of technology constraints."""

from __future__ import annotations

from mip import Constr, LinExpr, Model, Var, xsum

from .model_inputs import ModelInputs
from .technologies import battery, boiler, chp, heat_pump, heat_storage, local_resources
from .variables import ModelVariables


def add_capacity_constraint(
    model: Model, production_variable: Var, capacity_variable: Var
) -> LinExpr:
    """Add a production <= capacity relation and return the created constraint."""

    constraint = production_variable <= capacity_variable
    model += constraint
    return constraint


def add_electric_balance_constraint(
    model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int
) -> None:
    """Balance grid imports, generation, storage, demand, and electricity use."""

    flows = variables.flows
    model += (
        flows.z_D[time_index]
        + inputs.demand.pv_infeed[time_index]
        + xsum(
            variables.chp.chp_e[time_index][index]
            for index in variables.indices.chp
        )
        + xsum(
            variables.biomass_chp.bm_chp_e[time_index][index]
            for index in variables.indices.biomass_chp
        )
        + xsum(
            variables.battery.s_D[time_index][index]
            for index in variables.indices.battery
        )
        == inputs.demand.demand_electric[time_index]
        + flows.y_S_PV[time_index]
        + flows.y_S_CHP[time_index]
        + flows.y_S_BM_CHP[time_index]
        + xsum(
            variables.battery.s_C[time_index][index]
            for index in variables.indices.battery
        )
        + xsum(
            variables.heat_pump.hp_e[time_index][index]
            for index in variables.indices.heat_pump
        )
        + xsum(
            variables.river_heat_pump.electricity[time_index][index]
            for index in variables.indices.river_heat_pump
        )
        + xsum(
            variables.wwtp_heat_pump.electricity[time_index][index]
            for index in variables.indices.wwtp_heat_pump
        )
        + xsum(
            variables.electrode_boiler.eb_e[time_index][index]
            for index in variables.indices.electrode_boiler
        )
    )


def add_heat_balance_constraint(
    model: Model, inputs: ModelInputs, variables: ModelVariables, time_index: int
) -> Constr:
    """Balance all heat production, storage, demand, and dumped heat."""

    heat = variables
    model += (
        xsum(
            heat.chp.chp_h[time_index][index]
            for index in heat.indices.chp
        )
        + xsum(
            heat.heat_storage.hs_D[time_index][index]
            for index in heat.indices.heat_storage
        )
        + xsum(
            heat.boiler.hb_h[time_index][index]
            for index in heat.indices.boiler
        )
        + xsum(
            heat.heat_pump.hp_h[time_index][index]
            for index in heat.indices.heat_pump
        )
        + xsum(
            heat.river_heat_pump.heat[time_index][index]
            for index in heat.indices.river_heat_pump
        )
        + xsum(
            heat.wwtp_heat_pump.heat[time_index][index]
            for index in heat.indices.wwtp_heat_pump
        )
        + xsum(
            heat.electrode_boiler.eb_h[time_index][index]
            for index in heat.indices.electrode_boiler
        )
        + xsum(
            heat.industrial_excess_heat.ieh_h[time_index][index]
            * inputs.technologies.industrial_eh[index]["efficiency"]
            for index in heat.indices.industrial_eh
        )
        + xsum(
            heat.biomass_boiler.bm_hb_h[time_index][index]
            for index in heat.indices.biomass_boiler
        )
        + xsum(
            heat.biomass_chp.bm_chp_h[time_index][index]
            for index in heat.indices.biomass_chp
        )
        + xsum(
            heat.waste_to_energy.wte_h[time_index][index]
            * inputs.technologies.waste_to_energy[index]["efficiency"]
            for index in heat.indices.waste_to_energy
        )
        + xsum(
            heat.geothermal.geo_h[time_index][index]
            * inputs.technologies.geothermal[index]["efficiency"]
            for index in heat.indices.geothermal
        )
        + inputs.demand.solar_heat[time_index]
        == inputs.demand.demand_heat[time_index]
        + xsum(
            heat.heat_storage.hs_C[time_index][index]
            for index in heat.indices.heat_storage
        )
        + heat.flows.heat_dumped[time_index]
    )
    return model.constrs[-1]


def add_energy_balance_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Add the electric and heat balance for every model time step."""

    for time_index in variables.indices.time:
        add_electric_balance_constraint(model, inputs, variables, time_index)
        add_heat_balance_constraint(model, inputs, variables, time_index)


def add_static_technology_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Add time-independent relations in the historical technology order."""

    battery.add_static_constraints(model, inputs, variables)
    chp.add_static_constraints(model, inputs, variables)
    boiler.add_static_constraints(model, inputs, variables)
    heat_pump.add_static_constraints(model, inputs, variables)
    heat_storage.add_static_constraints(model, inputs, variables)
    boiler.add_electrode_static_constraints(model, inputs, variables)
    local_resources.add_industrial_excess_heat_constraints(model, inputs, variables)
    boiler.add_biomass_static_constraints(model, inputs, variables)
    chp.add_biomass_static_constraints(model, inputs, variables)
    local_resources.add_biomass_resource_limit(model, inputs, variables)
    local_resources.add_waste_to_energy_constraints(model, inputs, variables)
    local_resources.add_geothermal_constraints(model, inputs, variables)
    local_resources.add_river_capacity_constraints(model, inputs, variables)
    local_resources.add_wwtp_capacity_constraints(model, inputs, variables)


def add_time_step_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> tuple[Constr, ...]:
    """Add balances and all per-timestep technology constraints."""

    pv_infeed = inputs.demand.pv_infeed
    heat_balances = []
    for time_index in variables.indices.time:
        add_electric_balance_constraint(model, inputs, variables, time_index)
        heat_balances.append(add_heat_balance_constraint(model, inputs, variables, time_index))
        # The PV curtailment relation follows the two energy balances in the
        # original builder.
        model += variables.flows.y_S_PV[time_index] <= pv_infeed[time_index]
        battery.add_time_constraints(model, variables, time_index)
        chp.add_time_constraints(model, inputs, variables, time_index)
        boiler.add_time_constraints(model, inputs, variables, time_index)
        heat_pump.add_time_constraints(model, inputs, variables, time_index)
        heat_pump.add_river_time_constraints(model, inputs, variables, time_index)
        heat_pump.add_wwtp_time_constraints(model, inputs, variables, time_index)
        heat_storage.add_time_constraints(model, variables, time_index)
        boiler.add_electrode_time_constraints(model, inputs, variables, time_index)
        local_resources.add_industrial_time_constraint(
            model, inputs, variables, time_index
        )
        boiler.add_biomass_time_constraints(model, inputs, variables, time_index)
        chp.add_biomass_time_constraints(model, inputs, variables, time_index)
        local_resources.add_waste_to_energy_time_constraint(
            model, inputs, variables, time_index
        )
        local_resources.add_geothermal_time_constraint(
            model, inputs, variables, time_index
        )
    return tuple(heat_balances)


def add_storage_transition_constraints(
    model: Model, inputs: ModelInputs, variables: ModelVariables
) -> None:
    """Add intermediate and cyclic state-of-charge constraints."""

    # Keep the original order: intermediate battery, intermediate heat storage,
    # terminal heat storage, and terminal battery.
    battery.add_intermediate_state_constraints(model, inputs, variables)
    heat_storage.add_intermediate_state_constraints(model, inputs, variables)
    heat_storage.add_terminal_constraints(model, inputs, variables)
    battery.add_terminal_constraints(model, inputs, variables)


def add_constraints(model: Model, inputs: ModelInputs, variables: ModelVariables) -> tuple[Constr, ...]:
    """Compose shared balances and technology-specific constraint blocks."""

    add_static_technology_constraints(model, inputs, variables)
    heat_balances = add_time_step_constraints(model, inputs, variables)
    add_storage_transition_constraints(model, inputs, variables)
    return heat_balances


__all__ = [
    "add_capacity_constraint",
    "add_constraints",
    "add_electric_balance_constraint",
    "add_energy_balance_constraints",
    "add_heat_balance_constraint",
    "add_static_technology_constraints",
    "add_storage_transition_constraints",
    "add_time_step_constraints",
]
