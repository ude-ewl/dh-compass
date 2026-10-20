import json
from types import SimpleNamespace

from dh_compass import pipeline
from dh_compass.config import load_default_config


def test_allocation_survives_all_run_output_formats(tmp_path, monkeypatch):
    from dh_compass.reporting import charts, json_export, viewer_export

    metadata = {
        "method": "municipality_population", "energy_basis": "fuel", "fuel_budget_mwh": 14596.7075,
        "potential_sha256": "potential", "population_data": {"sha256": "population", "license": "dl-de/by-2-0"},
        "municipalities": [{"ags": "05958012", "population": 25424, "region_population": 3571898}],
    }
    monkeypatch.setattr(json_export, "build_full_results_json", lambda *_args, **_kwargs: {"summary": {}})
    monkeypatch.setattr(charts, "generate_all_charts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(viewer_export, "export_viewer_data", lambda **_kwargs: {"features": []})
    monkeypatch.setattr(viewer_export, "save_viewer_data",
                        lambda value, path, **_kwargs: json_export.save_full_results_json(value, path))
    monkeypatch.setattr(pipeline, "_write_network_geojson", lambda *_args: None)
    optimizer = SimpleNamespace(perf=SimpleNamespace(
        add_optimization_metric=lambda *_args: None, save_to_json=lambda *_args: None,
    ))
    prepared = SimpleNamespace(street_network=object(), lhd_graph=object(), buildings=[])
    pipeline.write_outputs(optimizer, [], prepared, load_default_config(),
                           output_dir=tmp_path, biomass_allocation=metadata)
    for filename in ("full_results.json", "viewer_data.json"):
        document = json.loads((tmp_path / filename).read_text(encoding="utf-8"))
        assert document["resource_allocations"]["biomass"] == metadata
    provenance = json.loads((tmp_path / "data_provenance.json").read_text(encoding="utf-8"))
    assert provenance["biomass"] == metadata
