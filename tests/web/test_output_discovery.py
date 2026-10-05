import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    __import__("importlib.util").util.find_spec("pydantic") is None,
    reason="web dependencies are not installed",
)


def _write_run(root: Path, *, malformed_full_results: bool = False) -> Path:
    run = root / "demo" / "20240101T000000Z"
    run.mkdir(parents=True)
    full_results = {
        "summary": {
            "total_subgraphs": 1,
            "connected_subgraphs": 1,
            "disconnected_subgraphs": 0,
            "total_heat_demand_mwh": 12.5,
            "connected_heat_demand_mwh": 12.5,
            "disconnected_heat_demand_mwh": 0,
            "connected_share_pct": 100,
        },
        "combined_graph": {
            "total_buildings": 2,
            "total_network_length_m": 100,
            "peak_load_kw": 4,
            "cost": {"total_annualized_eur": 2000},
        },
        "subgraphs": [],
    }
    (run / "full_results.json").write_text(
        "not json" if malformed_full_results else json.dumps(full_results),
        encoding="utf-8",
    )
    (run / "final_network.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    (run / "notes.txt").write_text("legacy output", encoding="utf-8")
    return run


def test_discovery_lists_legacy_runs_and_explicitly_marks_optional_files(tmp_path: Path) -> None:
    from dh_compass.web.services.output_discovery import OutputDiscoveryService

    _write_run(tmp_path)
    service = OutputDiscoveryService(tmp_path)

    runs = service.list_runs()

    assert len(runs) == 1
    manifest = runs[0]
    assert manifest.id == "demo/20240101T000000Z"
    assert manifest.scenario == "demo"
    artifacts = {artifact.id: artifact for artifact in manifest.artifacts}
    assert artifacts["full_results.json"].status == "available"
    assert artifacts["final_network.geojson"].status == "available"
    assert artifacts["viewer_data.json"].status == "missing"
    assert artifacts["performance_metrics.json"].status == "missing"
    for chart in (
        "chart_capacity.png",
        "chart_energy_shares.png",
        "chart_cost_structure.png",
        "chart_cost_detailed.png",
        "chart_cost_pie.png",
    ):
        assert artifacts[chart].status == "missing"
    assert artifacts["notes.txt"].status == "available"


def test_discovery_does_not_fail_the_manifest_for_a_malformed_optional_document(
    tmp_path: Path,
) -> None:
    from dh_compass.web.services.output_discovery import OutputDiscoveryService

    _write_run(tmp_path, malformed_full_results=True)
    manifest = OutputDiscoveryService(tmp_path).list_runs()[0]

    artifact = next(item for item in manifest.artifacts if item.id == "full_results.json")
    assert artifact.status == "invalid"
    assert manifest.summary is None


def test_artifact_resolution_rejects_paths_outside_the_run(tmp_path: Path) -> None:
    from dh_compass.web.services.output_discovery import OutputDiscoveryService

    _write_run(tmp_path)
    (tmp_path / "secret.txt").write_text("private", encoding="utf-8")
    service = OutputDiscoveryService(tmp_path)

    with pytest.raises(FileNotFoundError):
        service.resolve_artifact("demo/20240101T000000Z", "../secret.txt")
