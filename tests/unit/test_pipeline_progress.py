from __future__ import annotations

import pytest

from dh_compass import pipeline
from dh_compass.config import PreparedGeospatialData, ResourceAvailability, load_default_config
from dh_compass.observability.progress import CancellationRequested, CancellationToken


def test_pipeline_emits_stage_events_without_changing_stage_order(monkeypatch, tmp_path):
    config = load_default_config()
    inputs = {
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
    resources = ResourceAvailability()
    events: list[tuple[str, dict[str, object]]] = []

    class Observer:
        def emit(self, event_type, data=None):
            events.append((event_type, dict(data or {})))

    monkeypatch.setattr(pipeline, "prepare_geospatial_data", lambda *_: prepared)
    monkeypatch.setattr(pipeline, "build_optimization_context", lambda *_: object())
    monkeypatch.setattr(pipeline, "optimize_heat_grid", lambda *_args, **_kwargs: (object(), []))
    monkeypatch.setattr(
        pipeline,
        "write_outputs",
        lambda *_args, **_kwargs: (tmp_path / "run", {"summary": {}}, {"features": []}),
    )
    monkeypatch.setattr(
        pipeline,
        "assess_heat_resources",
        lambda *_args: resources,
    )

    result = pipeline.run_pipeline(
        config=config,
        inputs=inputs,
        observer=Observer(),
        cancellation_token=CancellationToken(),
    )

    assert result.output_dir == tmp_path / "run"
    assert [
        data["stage"]
        for event_type, data in events
        if event_type == "pipeline.stage_started"
    ] == [
        "load_inputs",
        "prepare_geospatial_data",
        "assess_heat_resources",
        "build_optimization_context",
        "optimize_heat_grid",
        "write_outputs",
    ]


def test_cancelled_token_is_checked_before_pipeline_work():
    token = CancellationToken()
    token.cancel()
    with pytest.raises(CancellationRequested):
        pipeline.run_pipeline(cancellation_token=token)
