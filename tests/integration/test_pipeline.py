from __future__ import annotations

from types import SimpleNamespace

from dh_compass import pipeline
from dh_compass.config import (
    PreparedGeospatialData,
    ResourceAvailability,
    load_default_config,
)


def test_run_pipeline_wires_stages_without_external_io(monkeypatch, tmp_path):
    config = load_default_config()
    loaded_inputs = {
        "buildings": object(),
        "bbox": (1.0, 2.0, 3.0, 4.0),
        "street_network": object(),
        "time_series": object(),
    }
    prepared = PreparedGeospatialData(
        buildings=object(),
        street_network=object(),
        lhd_graph=object(),
        subgraph_dict={},
        subgraph_attributes_df=object(),
    )
    resources = ResourceAvailability(industrial_eh_available=True)
    context = object()
    optimizer = object()
    optimization_results = [SimpleNamespace(subgraph_id=7, is_connected=False)]
    full_results = {"summary": {"total_subgraphs": 1}}
    viewer_data = {"features": []}
    calls = []

    def fake_load_inputs(received_config):
        calls.append(("load_inputs", received_config))
        return loaded_inputs

    def fake_prepare(received_inputs, received_config):
        calls.append(("prepare", received_inputs, received_config))
        return prepared

    def fake_assess(received_config, bbox):
        calls.append(("assess", received_config, bbox))
        return resources

    def fake_context(received_config, time_series, received_resources):
        calls.append(("context", received_config, time_series, received_resources))
        return context

    def fake_optimize(received_prepared, received_context, received_config):
        calls.append(("optimize", received_prepared, received_context, received_config))
        return optimizer, optimization_results

    def fake_write(
        received_optimizer,
        received_results,
        received_prepared,
        received_config,
        *,
        output_dir=None,
    ):
        calls.append(
            (
                "write",
                received_optimizer,
                received_results,
                received_prepared,
                received_config,
                output_dir,
            )
        )
        return tmp_path / "run", full_results, viewer_data

    monkeypatch.setattr(pipeline, "load_inputs", fake_load_inputs)
    monkeypatch.setattr(pipeline, "prepare_geospatial_data", fake_prepare)
    monkeypatch.setattr(pipeline, "assess_heat_resources", fake_assess)
    monkeypatch.setattr(pipeline, "build_optimization_context", fake_context)
    monkeypatch.setattr(pipeline, "optimize_heat_grid", fake_optimize)
    monkeypatch.setattr(pipeline, "write_outputs", fake_write)

    artifacts = pipeline.run_pipeline(config=config, output_dir=tmp_path / "requested")

    assert [call[0] for call in calls] == [
        "load_inputs",
        "prepare",
        "assess",
        "context",
        "optimize",
        "write",
    ]
    assert artifacts.config is config
    assert artifacts.prepared is prepared
    assert artifacts.resources is resources
    assert artifacts.optimizer is optimizer
    assert artifacts.optimization_results == optimization_results
    assert artifacts.output_dir == tmp_path / "run"
    assert artifacts.full_results == full_results
    assert artifacts.viewer_data == viewer_data
    assert calls[-1][-1] == tmp_path / "requested"


def test_pipeline_passes_weather_provenance_to_report(monkeypatch, tmp_path):
    import pandas as pd

    from dh_compass.config import TimeSeriesData

    config = load_default_config()
    data = pd.DataFrame({"Datum": pd.to_datetime(["2022-01-01T00:00Z"]), "temperature": [5]})
    data.attrs["weather"] = {"attribution": "Open-Meteo", "checksum": "test"}
    series = TimeSeriesData(data=data, timestamps=data["Datum"], length=1, days=1 / 24)
    prepared = object()
    inputs = {"buildings": object(), "bbox": object(), "street_network": object(), "time_series": series}
    monkeypatch.setattr(pipeline, "prepare_geospatial_data", lambda *_: prepared)
    monkeypatch.setattr(pipeline, "build_optimization_context", lambda *_: object())
    monkeypatch.setattr(pipeline, "optimize_heat_grid", lambda *_: (object(), []))
    captured = {}

    def write(*args, **kwargs):
        captured.update(kwargs)
        return tmp_path, {}, {}

    monkeypatch.setattr(pipeline, "write_outputs", write)
    pipeline.run_pipeline(config, inputs=inputs, resources=ResourceAvailability())
    assert captured["weather_metadata"] == data.attrs["weather"]
