import json
from importlib.util import find_spec
from pathlib import Path
from urllib.parse import quote

import pytest

pytestmark = pytest.mark.skipif(
    any(find_spec(name) is None for name in ("fastapi", "pydantic", "sqlalchemy")),
    reason="web dependencies are not installed",
)


def _write_run(root: Path) -> None:
    run = root / "demo" / "20240101T000000Z"
    run.mkdir(parents=True)
    (run / "full_results.json").write_text(
        json.dumps(
            {
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
                    "peak_load_kw": 4,
                    "total_network_length_m": 100,
                    "connection_length_m": 0,
                    "supply": {"heat_pump": {"annual_energy_mwh": 12.5}},
                    "cost": {
                        "total_annualized_eur": 2000,
                        "grid_annualized_eur": 600,
                        "supply_annualized_eur": 1400,
                    },
                },
                "subgraphs": [
                    {
                        "subgraph_id": 7,
                        "is_connected": True,
                        "annual_heat_demand_mwh": 12.5,
                        "peak_load_mw": 0.004,
                        "buildings": 2,
                        "total_network_length_m": 100,
                        "average_linear_heat_density_mwh_per_m_a": 2.5,
                        "edges": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run / "viewer_data.json").write_text(
        json.dumps(
            {
                "summary": {"total_subgraphs": 1, "connected_subgraphs": 1},
                "iterations": [
                    {
                        "step": 0,
                        "subgraph_id": 7,
                        "decision": "connected",
                        "central_cost_total": 2000,
                        "marginal_central_cost": 2000,
                        "decentral_cost": 2100,
                        "cumulative_connected_ids": [7],
                        "connecting_path_geojson": None,
                    }
                ],
                "subgraphs": {
                    "7": {
                        "is_connected": True,
                        "annual_heat_demand_mwh": 12.5,
                        "peak_load_kw": 4,
                        "buildings": 2,
                        "total_network_length_m": 100,
                        "avg_lhd": 2.5,
                        "central_cost": 2000,
                        "decentral_cost": 2100,
                        "central_grid_cost_raw": 5000,
                        "connection_length_m": 0,
                        "edges_geojson": {
                            "type": "FeatureCollection",
                            "features": [],
                        },
                        "clusters": [],
                        "supply": {"heat_pump": {"annual_energy_mwh": 12.5}},
                        "storage": {},
                        "total_heat_production_mwh": 12.5,
                    }
                },
                "lhd_edges_geojson": {"type": "FeatureCollection", "features": []},
                "potential_limits": {
                    "heat_pump": {"limit": 20, "unit": "MWh", "metric": "energy"}
                },
            }
        ),
        encoding="utf-8",
    )
    (run / "performance_metrics.json").write_text(
        json.dumps({"timing_stats": {"total": 1}}), encoding="utf-8"
    )
    (run / "final_network.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"type": "core"},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[7.0, 51.0], [7.1, 51.1]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run / "chart_cost_structure.png").write_bytes(b"png")


def test_legacy_combined_length_excludes_rejected_paths(tmp_path: Path) -> None:
    _write_run(tmp_path / "outputs")
    folder = tmp_path / "outputs" / "demo" / "20240101T000000Z"
    full_path = folder / "full_results.json"
    full = json.loads(full_path.read_text(encoding="utf-8"))
    full["combined_graph"].pop("connection_length_m")
    full_path.write_text(json.dumps(full), encoding="utf-8")
    viewer_path = folder / "viewer_data.json"
    viewer = json.loads(viewer_path.read_text(encoding="utf-8"))
    viewer["subgraphs"]["7"]["connection_length_m"] = 25
    viewer["subgraphs"]["8"] = {"is_connected": False, "connection_length_m": 999}
    viewer_path.write_text(json.dumps(viewer), encoding="utf-8")
    with _client(tmp_path) as client:
        run_id = quote("demo/20240101T000000Z", safe="")
        result = client.get(f"/api/v1/runs/{run_id}/results/summary").json()
        assert result["data"]["final_connection_length_m"] == 125
        assert result["data"]["average_linear_heat_density_mwh_per_m_a"] == 0.1
        assert result["source_artifacts"] == ["full_results.json", "viewer_data.json"]


def _client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
        output_root=tmp_path / "outputs",
        frontend_static_path=tmp_path / "missing-dist",
    )
    return TestClient(create_app(settings))


def test_read_only_result_endpoints_adapt_legacy_output(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    _write_run(output_root)

    with _client(tmp_path) as client:
        listing = client.get("/api/v1/runs")
        assert listing.status_code == 200
        body = listing.json()
        assert body["pagination"]["total"] == 1
        run_id = body["items"][0]["id"]
        encoded_id = quote(run_id, safe="")

        manifest = client.get(f"/api/v1/runs/{encoded_id}")
        assert manifest.status_code == 200
        assert manifest.json()["scenario"] == "demo"

        summary = client.get(f"/api/v1/runs/{encoded_id}/results/summary")
        assert summary.status_code == 200
        assert summary.json()["available"] is True
        assert summary.json()["data"]["connected_heat_demand_mwh"] == 12.5
        assert summary.json()["data"]["final_connection_length_m"] == 100
        assert summary.json()["data"]["average_linear_heat_density_mwh_per_m_a"] == 0.125

        network = client.get(f"/api/v1/runs/{encoded_id}/results/network")
        assert network.status_code == 200
        assert network.json()["data"]["final_network"]["type"] == "FeatureCollection"
        base_network = client.get(
            f"/api/v1/runs/{encoded_id}/results/network?layers=final_network"
        )
        assert base_network.json()["data"]["lhd"] is None
        assert base_network.json()["provenance"]["source_artifacts"] == [
            "final_network.geojson"
        ]

        iterations = client.get(f"/api/v1/runs/{encoded_id}/results/iterations")
        assert iterations.json()["data"][0]["decision"] == "connected"

        candidates = client.get(f"/api/v1/runs/{encoded_id}/results/candidates")
        assert candidates.json()["data"][0]["id"] == 7
        candidate = client.get(
            f"/api/v1/runs/{encoded_id}/results/candidates/7"
        )
        assert candidate.json()["data"]["decision"] == "connected"

        supply = client.get(f"/api/v1/runs/{encoded_id}/results/supply")
        assert supply.json()["data"]["supply"]["heat_pump"]["annual_energy_mwh"] == 12.5
        assert supply.json()["data"]["resources"]["heat_pump"] == {
            "used": 12.5,
            "limit": 20.0,
            "unit": "MWh",
            "utilization_pct": 62.5,
        }
        assert supply.json()["provenance"]["source_artifacts"] == [
            "full_results.json",
            "viewer_data.json",
        ]
        costs = client.get(f"/api/v1/runs/{encoded_id}/results/costs")
        assert costs.json()["data"]["total_annualized_eur"] == 2000

        artifacts = client.get(f"/api/v1/runs/{encoded_id}/artifacts")
        artifact = next(
            item for item in artifacts.json()["items"] if item["id"] == "full_results.json"
        )
        download = client.get(
            f"/api/v1/runs/{encoded_id}/artifacts/{quote(artifact['id'], safe='')}/download"
        )
        assert download.status_code == 200
        assert download.json()["summary"]["connected_subgraphs"] == 1


def test_adapter_uses_report_fixtures_and_omits_rejected_connection_paths(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "outputs"
    run = output_root / "fixture" / "20240101T000000Z"
    run.mkdir(parents=True)
    fixture_root = Path(__file__).parents[1] / "fixtures"
    for artifact in ("full_results.json", "viewer_data.json"):
        (run / artifact).write_bytes((fixture_root / artifact).read_bytes())

    with _client(tmp_path) as client:
        run_id = quote("fixture/20240101T000000Z", safe="")
        summary = client.get(f"/api/v1/runs/{run_id}/results/summary")
        assert summary.status_code == 200
        assert summary.json()["data"]["connected_heat_demand_mwh"] == 12.5

        candidates = client.get(f"/api/v1/runs/{run_id}/results/candidates")
        assert [item["id"] for item in candidates.json()["data"]] == [1, 2, 3]

        network = client.get(f"/api/v1/runs/{run_id}/results/network")
        paths = network.json()["data"]["connection_paths"]["features"]
        assert len(paths) == 1
        assert paths[0]["properties"] == {
            "candidate_id": 3,
            "decision": "connected",
            "step": 2,
        }


def test_missing_optional_result_is_explicit_and_downloads_are_confined(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "outputs"
    run = output_root / "demo" / "20240101T000000Z"
    run.mkdir(parents=True)
    (run / "full_results.json").write_text(json.dumps({"summary": {"x": 1}}), encoding="utf-8")
    (tmp_path / "secret.txt").write_text("private", encoding="utf-8")

    with _client(tmp_path) as client:
        run_id = quote("demo/20240101T000000Z", safe="")
        iterations = client.get(f"/api/v1/runs/{run_id}/results/iterations")
        assert iterations.status_code == 200
        assert iterations.json()["available"] is False
        assert iterations.json()["data"] is None

        traversal = client.get(
            f"/api/v1/runs/{run_id}/artifacts/{quote('../secret.txt', safe='')}/download"
        )
        assert traversal.status_code == 404
        assert "private" not in traversal.text


def test_dedicated_decentral_timeseries_and_etag_endpoints(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    _write_run(output_root)
    run = output_root / "demo" / "20240101T000000Z"
    (run / "timeseries.json").write_text(
        json.dumps(
            {
                "timestamps": list(range(12)),
                "series": {
                    "demand_heat": [float(index) for index in range(12)],
                    "temperature": [10.0 + index for index in range(12)],
                },
            }
        ),
        encoding="utf-8",
    )

    with _client(tmp_path) as client:
        run_id = quote("demo/20240101T000000Z", safe="")
        summary = client.get(f"/api/v1/runs/{run_id}/results/summary")
        assert summary.status_code == 200
        assert summary.headers["etag"]
        assert summary.json()["provenance"]["source_artifacts"] == ["full_results.json"]
        assert summary.json()["availability"]["result"] is True
        cached = client.get(
            f"/api/v1/runs/{run_id}/results/summary",
            headers={"If-None-Match": summary.headers["etag"]},
        )
        assert cached.status_code == 304

        decentral = client.get(f"/api/v1/runs/{run_id}/results/decentral")
        assert decentral.status_code == 200
        assert decentral.json()["data"][0]["decentral_cost"] == 2100.0
        assert decentral.json()["data"][0]["difference_eur"] == 100.0

        timeseries = client.get(
            f"/api/v1/runs/{run_id}/results/timeseries?series=demand_heat&resolution=4"
        )
        assert timeseries.status_code == 200
        data = timeseries.json()["data"]
        assert data["series_names"] == ["demand_heat"]
        assert data["returned_points"] == 4
        assert data["original_points"] == 12
        assert data["downsampled"] is True
