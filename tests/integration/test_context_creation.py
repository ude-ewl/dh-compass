from dataclasses import replace
from math import nan

import pandas as pd
import pytest

from dh_compass.config import load_default_config
from dh_compass.demand import runtime
from dh_compass.demand.runtime import build_technology_inputs, load_time_series
from dh_compass.optimization.context import build_optimization_context


@pytest.fixture
def local_calendar_config(project_root, tmp_path, monkeypatch):
    """Context wiring uses a test calendar rather than a provider workbook."""
    config = load_default_config(project_root=project_root)
    path = tmp_path / "calendar.xlsx"
    path.touch()
    dates = pd.date_range("2022-01-01", "2023-01-01", freq="h", inclusive="left")
    reference = pd.DataFrame({"Datum": dates})
    monkeypatch.setattr(runtime, "read_ts_data", lambda *_: (reference, len(reference), 365))
    return replace(config, paths=config.paths.with_overrides({"historical_timeseries": path}))

def test_context_creation_uses_explicit_runtime_inputs(local_calendar_config, mocked_weather):
    config = local_calendar_config
    series = load_time_series(config.paths, config)
    inputs = build_technology_inputs(config.paths, config, series)
    context = build_optimization_context(config, series, technology_inputs=inputs)

    assert len(context.market.central.timestamps) == series.length
    assert len(context.demand.cop_decentral) == series.length
    assert context.network.pipeline_cost_per_m == config.network.pipeline_cost_per_m
    assert context.runtime_services.building_profile_generator is not None
    assert context.market.central.timestamps is inputs.timestamps
    assert context.technologies.central.boiler is inputs.boiler_central


def test_context_rejects_nonfinite_pipeline_residual(local_calendar_config, mocked_weather):
    config = local_calendar_config
    series = load_time_series(config.paths, config)
    inputs = build_technology_inputs(config.paths, config, series)
    context = build_optimization_context(config, series, technology_inputs=inputs)

    invalid_network = replace(context.network, residual_value_factor_pipeline=nan)
    with pytest.raises(
        ValueError,
        match="network.residual_value_factor_pipeline must be a finite number",
    ):
        replace(context, network=invalid_network)
