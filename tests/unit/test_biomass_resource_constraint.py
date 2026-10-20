from types import SimpleNamespace

import pytest

from dh_compass.optimization.technologies import local_resources


@pytest.mark.parametrize("boiler,chp,dt,budget,feasible", [
    # Individually both fit 100 kWh, together they exceed it.
    ([30.0], [25.0], 2.0, 0.1, False),
    ([30.0], [20.0], 2.0, 0.1, True),
    # Every timestep and technology type consumes the same municipal fuel pool.
    ([10.0, 15.0], [20.0, 10.0], 2.0, 0.1, False),
])
def test_boiler_and_chp_share_one_annual_fuel_input_budget(monkeypatch, boiler, chp, dt, budget, feasible):
    monkeypatch.setattr(local_resources, "xsum", sum)
    constraints = []

    class Model:
        def __iadd__(self, constraint):
            constraints.append(constraint)
            return self

    variables = SimpleNamespace(
        biomass_boiler=SimpleNamespace(bm_hb_f=[[value] for value in boiler]),
        biomass_chp=SimpleNamespace(bm_chp_f=[[value] for value in chp]),
        indices=SimpleNamespace(time=range(len(boiler)), biomass_boiler=[0], biomass_chp=[0]),
    )
    inputs = SimpleNamespace(
        resources=SimpleNamespace(biomass_energy_limit_mwh=budget),
        market=SimpleNamespace(dt=dt), options=SimpleNamespace(decentral_bool=0),
    )
    local_resources.add_biomass_resource_limit(Model(), inputs, variables)
    assert constraints == [feasible]
