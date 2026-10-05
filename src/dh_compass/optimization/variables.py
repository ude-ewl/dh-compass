"""Variable containers and creation for the optimization model.

The solver model still uses the historical variable names.  This module only
owns the creation of those variables and groups the resulting arrays by their
mathematical role so constraint and objective code does not need to manipulate
large, positional tuples.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mip import Model, Var

from .model_inputs import ModelInputs


def time_indices(timestamps: Sequence[object]) -> range:
    """Return the model time-index range for a timestamp sequence."""

    return range(len(timestamps))


def reduced_time_indices(timestamps: Sequence[object]) -> range:
    """Return indices with a successor for storage state constraints."""

    return range(max(0, len(timestamps) - 1))


@dataclass(frozen=True)
class ModelIndices:
    """Index ranges shared by all variable and constraint builders."""

    time: range
    reduced_time: range
    battery: range
    chp: range
    boiler: range
    heat_pump: range
    electrode_boiler: range
    heat_storage: range
    industrial_eh: range
    biomass_boiler: range
    biomass_chp: range
    waste_to_energy: range
    geothermal: range
    river_heat_pump: range
    wwtp_heat_pump: range

    @classmethod
    def from_inputs(cls, inputs: ModelInputs) -> "ModelIndices":
        technologies = inputs.technologies
        time = time_indices(inputs.market.timestamps)
        return cls(
            time=time,
            reduced_time=reduced_time_indices(inputs.market.timestamps),
            battery=range(len(technologies.battery_storage)),
            chp=range(len(technologies.chp)),
            boiler=range(len(technologies.boiler)),
            heat_pump=range(len(technologies.heat_pump)),
            electrode_boiler=range(len(technologies.electrode_boiler)),
            heat_storage=range(len(technologies.heat_storage)),
            industrial_eh=range(len(technologies.industrial_eh)),
            biomass_boiler=range(len(technologies.biomass_boiler)),
            biomass_chp=range(len(technologies.biomass_chp)),
            waste_to_energy=range(len(technologies.waste_to_energy)),
            geothermal=range(len(technologies.geothermal)),
            river_heat_pump=range(len(technologies.river_heat_pump)),
            wwtp_heat_pump=range(len(technologies.wwtp_heat_pump)),
        )


@dataclass
class FlowVariables:
    """Variables shared by the electricity and heat balances."""

    y_S_PV: list[Var]
    y_S_CHP: list[Var]
    z_D: list[Var]
    heat_dumped: list[Var]
    y_S_BM_CHP: list[Var]


@dataclass
class BatteryVariables:
    """Battery dispatch, state, and sizing variables."""

    s_C: list[list[Var]]
    s_D: list[list[Var]]
    L_S: list[list[Var]]
    capacity_bs: list[Var]
    power_bs: list[Var]


@dataclass
class CHPVariables:
    """CHP dispatch and sizing variables."""

    chp_e: list[list[Var]]
    chp_h: list[list[Var]]
    chp_f: list[list[Var]]
    power_chp: list[Var]
    power_heat_chp: list[Var]
    power_fuel_chp: list[Var]


@dataclass
class HeatStorageVariables:
    """Heat-storage dispatch, state, and sizing variables."""

    hs_C: list[list[Var]]
    hs_D: list[list[Var]]
    hs_S: list[list[Var]]
    capacity_hs: list[Var]
    power_hs: list[Var]


@dataclass
class BoilerVariables:
    """Gas boiler dispatch and sizing variables."""

    hb_h: list[list[Var]]
    hb_f: list[list[Var]]
    power_heat_boiler: list[Var]


@dataclass
class HeatPumpVariables:
    """Air-source heat-pump dispatch and sizing variables."""

    hp_e: list[list[Var]]
    hp_h: list[list[Var]]
    power_heat_heat_pump: list[Var]


@dataclass
class ElectrodeBoilerVariables:
    """Electrode-boiler dispatch and sizing variables."""

    eb_e: list[list[Var]]
    eb_h: list[list[Var]]
    power_eb: list[Var]


@dataclass
class IndustrialExcessHeatVariables:
    """Industrial excess-heat dispatch and sizing variables."""

    ieh_h: list[list[Var]]
    power_ieh: list[Var]


@dataclass
class BiomassBoilerVariables:
    """Biomass-boiler dispatch and sizing variables."""

    bm_hb_h: list[list[Var]]
    bm_hb_f: list[list[Var]]
    power_bm_hb: list[Var]


@dataclass
class BiomassCHPVariables:
    """Biomass CHP dispatch and sizing variables."""

    bm_chp_e: list[list[Var]]
    bm_chp_h: list[list[Var]]
    bm_chp_f: list[list[Var]]
    power_bm_chp: list[Var]
    power_heat_bm_chp: list[Var]
    power_fuel_bm_chp: list[Var]


@dataclass
class WasteToEnergyVariables:
    """Waste-to-energy dispatch and sizing variables."""

    wte_h: list[list[Var]]
    power_wte: list[Var]


@dataclass
class GeothermalVariables:
    """Geothermal dispatch and sizing variables."""

    geo_h: list[list[Var]]
    power_geo: list[Var]


@dataclass
class SourceHeatPumpVariables:
    """Dispatch and sizing variables for a source-specific heat pump."""

    heat: list[list[Var]]
    electricity: list[list[Var]]
    power: list[Var]


@dataclass
class ModelVariables:
    """All variables created for one model, grouped by technology and flow."""

    indices: ModelIndices
    flows: FlowVariables
    battery: BatteryVariables
    chp: CHPVariables
    heat_storage: HeatStorageVariables
    boiler: BoilerVariables
    heat_pump: HeatPumpVariables
    electrode_boiler: ElectrodeBoilerVariables
    industrial_excess_heat: IndustrialExcessHeatVariables
    biomass_boiler: BiomassBoilerVariables
    biomass_chp: BiomassCHPVariables
    waste_to_energy: WasteToEnergyVariables
    geothermal: GeothermalVariables
    river_heat_pump: SourceHeatPumpVariables
    wwtp_heat_pump: SourceHeatPumpVariables

    # These aliases keep the historical variable identifiers convenient for
    # diagnostics and for small integrations that consume this container.
    @property
    def y_S_PV(self) -> list[Var]:
        return self.flows.y_S_PV

    @property
    def y_S_CHP(self) -> list[Var]:
        return self.flows.y_S_CHP

    @property
    def z_D(self) -> list[Var]:
        return self.flows.z_D

    @property
    def heat_dumped(self) -> list[Var]:
        return self.flows.heat_dumped

    @property
    def y_S_BM_CHP(self) -> list[Var]:
        return self.flows.y_S_BM_CHP

    @property
    def s_C(self) -> list[list[Var]]:
        return self.battery.s_C

    @property
    def s_D(self) -> list[list[Var]]:
        return self.battery.s_D

    @property
    def L_S(self) -> list[list[Var]]:
        return self.battery.L_S

    @property
    def capacity_bs(self) -> list[Var]:
        return self.battery.capacity_bs

    @property
    def power_bs(self) -> list[Var]:
        return self.battery.power_bs

    @property
    def chp_e(self) -> list[list[Var]]:
        return self.chp.chp_e

    @property
    def chp_h(self) -> list[list[Var]]:
        return self.chp.chp_h

    @property
    def chp_f(self) -> list[list[Var]]:
        return self.chp.chp_f

    @property
    def power_chp(self) -> list[Var]:
        return self.chp.power_chp

    @property
    def power_heat_chp(self) -> list[Var]:
        return self.chp.power_heat_chp

    @property
    def power_fuel_chp(self) -> list[Var]:
        return self.chp.power_fuel_chp

    @property
    def hs_C(self) -> list[list[Var]]:
        return self.heat_storage.hs_C

    @property
    def hs_D(self) -> list[list[Var]]:
        return self.heat_storage.hs_D

    @property
    def hs_S(self) -> list[list[Var]]:
        return self.heat_storage.hs_S

    @property
    def capacity_hs(self) -> list[Var]:
        return self.heat_storage.capacity_hs

    @property
    def power_hs(self) -> list[Var]:
        return self.heat_storage.power_hs

    @property
    def hb_h(self) -> list[list[Var]]:
        return self.boiler.hb_h

    @property
    def hb_f(self) -> list[list[Var]]:
        return self.boiler.hb_f

    @property
    def power_heat_boiler(self) -> list[Var]:
        return self.boiler.power_heat_boiler

    @property
    def hp_e(self) -> list[list[Var]]:
        return self.heat_pump.hp_e

    @property
    def hp_h(self) -> list[list[Var]]:
        return self.heat_pump.hp_h

    @property
    def power_heat_heat_pump(self) -> list[Var]:
        return self.heat_pump.power_heat_heat_pump

    @property
    def eb_e(self) -> list[list[Var]]:
        return self.electrode_boiler.eb_e

    @property
    def eb_h(self) -> list[list[Var]]:
        return self.electrode_boiler.eb_h

    @property
    def power_eb(self) -> list[Var]:
        return self.electrode_boiler.power_eb

    @property
    def ieh_h(self) -> list[list[Var]]:
        return self.industrial_excess_heat.ieh_h

    @property
    def power_ieh(self) -> list[Var]:
        return self.industrial_excess_heat.power_ieh

    @property
    def bm_hb_h(self) -> list[list[Var]]:
        return self.biomass_boiler.bm_hb_h

    @property
    def bm_hb_f(self) -> list[list[Var]]:
        return self.biomass_boiler.bm_hb_f

    @property
    def power_bm_hb(self) -> list[Var]:
        return self.biomass_boiler.power_bm_hb

    @property
    def bm_chp_e(self) -> list[list[Var]]:
        return self.biomass_chp.bm_chp_e

    @property
    def bm_chp_h(self) -> list[list[Var]]:
        return self.biomass_chp.bm_chp_h

    @property
    def bm_chp_f(self) -> list[list[Var]]:
        return self.biomass_chp.bm_chp_f

    @property
    def power_bm_chp(self) -> list[Var]:
        return self.biomass_chp.power_bm_chp

    @property
    def power_heat_bm_chp(self) -> list[Var]:
        return self.biomass_chp.power_heat_bm_chp

    @property
    def power_fuel_bm_chp(self) -> list[Var]:
        return self.biomass_chp.power_fuel_bm_chp

    @property
    def wte_h(self) -> list[list[Var]]:
        return self.waste_to_energy.wte_h

    @property
    def power_wte(self) -> list[Var]:
        return self.waste_to_energy.power_wte

    @property
    def geo_h(self) -> list[list[Var]]:
        return self.geothermal.geo_h

    @property
    def power_geo(self) -> list[Var]:
        return self.geothermal.power_geo

    @property
    def hp_river_h(self) -> list[list[Var]]:
        return self.river_heat_pump.heat

    @property
    def hp_river_e(self) -> list[list[Var]]:
        return self.river_heat_pump.electricity

    @property
    def power_hp_river(self) -> list[Var]:
        return self.river_heat_pump.power

    @property
    def hp_wwtp_h(self) -> list[list[Var]]:
        return self.wwtp_heat_pump.heat

    @property
    def hp_wwtp_e(self) -> list[list[Var]]:
        return self.wwtp_heat_pump.electricity

    @property
    def power_hp_wwtp(self) -> list[Var]:
        return self.wwtp_heat_pump.power

    @property
    def time_indices(self) -> range:
        return self.indices.time

    @property
    def reduced_time_indices(self) -> range:
        return self.indices.reduced_time


def _time_variables(model: Model, name: str, time_indices: range) -> list[Var]:
    return [model.add_var(lb=0, name=name) for _ in time_indices]


def _technology_time_variables(
    model: Model, name: str, time_indices: range, technology_indices: range
) -> list[list[Var]]:
    return [
        [model.add_var(lb=0, name=name) for _ in technology_indices]
        for _ in time_indices
    ]


def _sizing_variables(model: Model, name: str, technology_indices: range) -> list[Var]:
    return [model.add_var(name=name, lb=0) for _ in technology_indices]


def create_variables(model: Model, inputs: ModelInputs) -> ModelVariables:
    """Create all model variables without adding any algebraic constraints.

    Creation order and names intentionally match the legacy model.  In
    particular, this keeps existing result extraction and solver diagnostics
    stable while allowing the mathematical sections to use typed containers.
    """

    indices = ModelIndices.from_inputs(inputs)
    t = indices.time

    # Time-dependent variables.  Keep this order stable: the legacy gathering
    # helper groups solver variables using the first variable of each block.
    y_S_PV = _time_variables(model, "y_S_PV", t)
    y_S_CHP = _time_variables(model, "y_S_CHP", t)
    z_D = _time_variables(model, "z_D", t)
    s_C = _technology_time_variables(model, "s_C", t, indices.battery)
    s_D = _technology_time_variables(model, "s_D", t, indices.battery)
    L_S = _technology_time_variables(model, "L_S", t, indices.battery)
    chp_e = _technology_time_variables(model, "chp_e", t, indices.chp)
    chp_h = _technology_time_variables(model, "chp_h", t, indices.chp)
    chp_f = _technology_time_variables(model, "chp_f", t, indices.chp)
    hs_C = _technology_time_variables(model, "hs_C", t, indices.heat_storage)
    hs_D = _technology_time_variables(model, "hs_D", t, indices.heat_storage)
    hs_S = _technology_time_variables(model, "hs_S", t, indices.heat_storage)
    hb_h = _technology_time_variables(model, "hb_h", t, indices.boiler)
    hb_f = _technology_time_variables(model, "hb_f", t, indices.boiler)
    hp_e = _technology_time_variables(model, "hp_e", t, indices.heat_pump)
    hp_h = _technology_time_variables(model, "hp_h", t, indices.heat_pump)
    heat_dumped = _time_variables(model, "heat_dumped", t)
    eb_e = _technology_time_variables(model, "eb_e", t, indices.electrode_boiler)
    eb_h = _technology_time_variables(model, "eb_h", t, indices.electrode_boiler)
    ieh_h = _technology_time_variables(model, "ieh_h", t, indices.industrial_eh)
    bm_hb_h = _technology_time_variables(model, "bm_hb_h", t, indices.biomass_boiler)
    bm_hb_f = _technology_time_variables(model, "bm_hb_f", t, indices.biomass_boiler)
    bm_chp_e = _technology_time_variables(model, "bm_chp_e", t, indices.biomass_chp)
    bm_chp_h = _technology_time_variables(model, "bm_chp_h", t, indices.biomass_chp)
    bm_chp_f = _technology_time_variables(model, "bm_chp_f", t, indices.biomass_chp)
    y_S_BM_CHP = _time_variables(model, "y_S_BM_CHP", t)
    wte_h = _technology_time_variables(model, "wte_h", t, indices.waste_to_energy)
    geo_h = _technology_time_variables(model, "geo_h", t, indices.geothermal)
    hp_river_h = _technology_time_variables(model, "hp_river_h", t, indices.river_heat_pump)
    hp_river_e = _technology_time_variables(model, "hp_river_e", t, indices.river_heat_pump)
    hp_wwtp_h = _technology_time_variables(model, "hp_wwtp_h", t, indices.wwtp_heat_pump)
    hp_wwtp_e = _technology_time_variables(model, "hp_wwtp_e", t, indices.wwtp_heat_pump)

    # Capacity and power variables.
    power_heat_boiler = _sizing_variables(model, "power_heat_boiler", indices.boiler)
    power_chp = _sizing_variables(model, "power_chp", indices.chp)
    power_heat_chp = _sizing_variables(model, "power_heat_chp", indices.chp)
    power_fuel_chp = _sizing_variables(model, "power_fuel_chp", indices.chp)
    power_heat_heat_pump = _sizing_variables(
        model, "power_heat_heat_pump", indices.heat_pump
    )
    capacity_hs = _sizing_variables(model, "capacity_hs", indices.heat_storage)
    power_hs = _sizing_variables(model, "power_hs", indices.heat_storage)
    capacity_bs = _sizing_variables(model, "capacity_bs", indices.battery)
    power_bs = _sizing_variables(model, "power_bs", indices.battery)
    power_eb = _sizing_variables(model, "power_eb", indices.electrode_boiler)
    power_ieh = _sizing_variables(model, "power_ieh", indices.industrial_eh)
    power_wte = _sizing_variables(model, "power_wte", indices.waste_to_energy)
    power_geo = _sizing_variables(model, "power_geo", indices.geothermal)
    power_hp_river = _sizing_variables(
        model, "power_hp_river", indices.river_heat_pump
    )
    power_hp_wwtp = _sizing_variables(
        model, "power_hp_wwtp", indices.wwtp_heat_pump
    )
    power_bm_hb = _sizing_variables(model, "power_bm_hb", indices.biomass_boiler)
    power_bm_chp = _sizing_variables(model, "power_bm_chp", indices.biomass_chp)
    power_heat_bm_chp = _sizing_variables(
        model, "power_heat_bm_chp", indices.biomass_chp
    )
    power_fuel_bm_chp = _sizing_variables(
        model, "power_fuel_bm_chp", indices.biomass_chp
    )

    return ModelVariables(
        indices=indices,
        flows=FlowVariables(
            y_S_PV=y_S_PV,
            y_S_CHP=y_S_CHP,
            z_D=z_D,
            heat_dumped=heat_dumped,
            y_S_BM_CHP=y_S_BM_CHP,
        ),
        battery=BatteryVariables(
            s_C=s_C,
            s_D=s_D,
            L_S=L_S,
            capacity_bs=capacity_bs,
            power_bs=power_bs,
        ),
        chp=CHPVariables(
            chp_e=chp_e,
            chp_h=chp_h,
            chp_f=chp_f,
            power_chp=power_chp,
            power_heat_chp=power_heat_chp,
            power_fuel_chp=power_fuel_chp,
        ),
        heat_storage=HeatStorageVariables(
            hs_C=hs_C,
            hs_D=hs_D,
            hs_S=hs_S,
            capacity_hs=capacity_hs,
            power_hs=power_hs,
        ),
        boiler=BoilerVariables(
            hb_h=hb_h,
            hb_f=hb_f,
            power_heat_boiler=power_heat_boiler,
        ),
        heat_pump=HeatPumpVariables(
            hp_e=hp_e,
            hp_h=hp_h,
            power_heat_heat_pump=power_heat_heat_pump,
        ),
        electrode_boiler=ElectrodeBoilerVariables(
            eb_e=eb_e,
            eb_h=eb_h,
            power_eb=power_eb,
        ),
        industrial_excess_heat=IndustrialExcessHeatVariables(
            ieh_h=ieh_h,
            power_ieh=power_ieh,
        ),
        biomass_boiler=BiomassBoilerVariables(
            bm_hb_h=bm_hb_h,
            bm_hb_f=bm_hb_f,
            power_bm_hb=power_bm_hb,
        ),
        biomass_chp=BiomassCHPVariables(
            bm_chp_e=bm_chp_e,
            bm_chp_h=bm_chp_h,
            bm_chp_f=bm_chp_f,
            power_bm_chp=power_bm_chp,
            power_heat_bm_chp=power_heat_bm_chp,
            power_fuel_bm_chp=power_fuel_bm_chp,
        ),
        waste_to_energy=WasteToEnergyVariables(wte_h=wte_h, power_wte=power_wte),
        geothermal=GeothermalVariables(geo_h=geo_h, power_geo=power_geo),
        river_heat_pump=SourceHeatPumpVariables(
            heat=hp_river_h, electricity=hp_river_e, power=power_hp_river
        ),
        wwtp_heat_pump=SourceHeatPumpVariables(
            heat=hp_wwtp_h, electricity=hp_wwtp_e, power=power_hp_wwtp
        ),
    )


__all__ = [
    "BatteryVariables",
    "BiomassBoilerVariables",
    "BiomassCHPVariables",
    "BoilerVariables",
    "CHPVariables",
    "ElectrodeBoilerVariables",
    "FlowVariables",
    "GeothermalVariables",
    "HeatPumpVariables",
    "HeatStorageVariables",
    "IndustrialExcessHeatVariables",
    "ModelIndices",
    "ModelVariables",
    "SourceHeatPumpVariables",
    "WasteToEnergyVariables",
    "create_variables",
    "reduced_time_indices",
    "time_indices",
]
