from __future__ import annotations

import io
import json
import zipfile
from importlib.util import find_spec
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    any(find_spec(name) is None for name in ("fastapi", "pydantic", "sqlalchemy")),
    reason="web dependencies are not installed",
)


def _write_run(root: Path, timestamp: str) -> str:
    run = root / "demo" / timestamp
    run.mkdir(parents=True)
    fixtures = Path(__file__).parents[1] / "fixtures"
    for name in ("full_results.json", "viewer_data.json"):
        (run / name).write_bytes((fixtures / name).read_bytes())
    (run / "performance_metrics.json").write_text(
        json.dumps({"timing_stats": {"total": 1}}), encoding="utf-8"
    )
    (run / "final_network.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    (run / "run.log").write_text("worker completed\n", encoding="utf-8")
    # This is deliberately not a DH-COMPASS artifact. A reproducibility
    # bundle must not turn arbitrary output-directory files into downloads.
    (run / ".env").write_text("API_TOKEN=not-for-export\n", encoding="utf-8")
    return f"demo/{timestamp}"


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


def test_comparison_and_reproducibility_exports(tmp_path: Path) -> None:
    first = _write_run(tmp_path / "outputs", "20240101T000000Z")
    second = _write_run(tmp_path / "outputs", "20240102T000000Z")

    with _client(tmp_path) as client:
        comparison = client.post(
            "/api/v1/comparisons", json={"run_ids": [first, second]}
        )
        assert comparison.status_code == 201
        body = comparison.json()
        assert body["run_ids"] == [first, second]
        assert len(body["compatibility"]) == 4
        assert body["kpis"] == body["kpi_differences"]

        stored = client.get(f"/api/v1/comparisons/{body['id']}")
        assert stored.status_code == 200
        assert stored.json()["id"] == body["id"]

        csv_response = client.get(
            f"/api/v1/runs/{first.replace('/', '%2F')}/exports/candidates.csv"
        )
        assert csv_response.status_code == 200
        assert "decision" in csv_response.content.decode("utf-8-sig").splitlines()[0]

        report = client.post(f"/api/v1/runs/{first.replace('/', '%2F')}/reports")
        assert report.status_code == 202
        assert report.json()["status"] == "queued"

        csv_job = client.post(
            f"/api/v1/runs/{first.replace('/', '%2F')}/exports/csv",
            json={},
        )
        assert csv_job.status_code == 202
        assert csv_job.json()["kind"] == "csv"
        assert csv_job.json()["status"] == "queued"

        bundle = client.post(f"/api/v1/runs/{first.replace('/', '%2F')}/bundles")
        assert bundle.status_code == 202
        assert bundle.json()["status"] == "queued"

        from dh_compass.web.services.exports import ExportService
        from dh_compass.web.services.output_discovery import OutputDiscoveryService

        service = ExportService(
            OutputDiscoveryService(tmp_path / "outputs"),
            output_root=tmp_path / "outputs",
            project_root=tmp_path,
            engine=client.app.state.metadata_engine,
        )
        generated_bundle = service.generate(bundle.json()["id"])
        download = client.get(f"/api/v1/exports/{generated_bundle['id']}/download")
        assert download.status_code == 200
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            names = set(archive.namelist())
        assert {"run_manifest.json", "configuration.toml", "checksums.sha256"}.issubset(names)
        assert "full_results.json" in names
        assert "final_network.geojson" in names
        assert "performance_metrics.json" in names
        assert "run.log" in names
        assert ".env" not in names

        from dh_compass.web.persistence.repositories import AuditRepository

        actions = {
            item["action"]
            for item in AuditRepository(client.app.state.metadata_engine).list()
        }
        assert {
            "comparison.created",
            "export.report_requested",
            "export.bundle_requested",
            "export.downloaded",
        }.issubset(actions)


def test_export_retention_does_not_remove_run_output(tmp_path: Path) -> None:
    run_id = _write_run(tmp_path / "outputs", "20240101T000000Z")
    with _client(tmp_path) as client:
        report = client.post(f"/api/v1/runs/{run_id.replace('/', '%2F')}/reports")
        export_id = report.json()["id"]
        from dh_compass.web.services.exports import ExportService
        from dh_compass.web.services.output_discovery import OutputDiscoveryService

        ExportService(
            OutputDiscoveryService(tmp_path / "outputs"),
            output_root=tmp_path / "outputs",
            project_root=tmp_path,
            engine=client.app.state.metadata_engine,
        ).generate(export_id)
        cleanup = client.post(
            "/api/v1/maintenance/retention/cleanup",
            params={"older_than_days": 0},
        )
        assert cleanup.status_code == 200
        assert cleanup.json()["run_artifacts_preserved"] is True
        assert (
            tmp_path / "outputs" / "demo" / "20240101T000000Z" / "full_results.json"
        ).is_file()
        assert client.get(f"/api/v1/exports/{export_id}").json()["status"] == "failed"


def test_enqueue_returns_before_export_generation(tmp_path: Path) -> None:
    run_id = _write_run(tmp_path / "outputs", "20240101T000000Z")
    with _client(tmp_path) as client:
        from dh_compass.web.services.exports import ExportService
        from dh_compass.web.services.output_discovery import OutputDiscoveryService

        service = ExportService(
            OutputDiscoveryService(tmp_path / "outputs"),
            output_root=tmp_path / "outputs",
            project_root=tmp_path,
            engine=client.app.state.metadata_engine,
        )
        queued = service.enqueue(run_id, "bundle")
        assert queued["status"] == "queued"
        assert queued["storage_key"] is None

        generated = service.generate(str(queued["id"]))
        assert generated["status"] == "available"


def test_csv_text_values_are_safe_for_spreadsheets() -> None:
    from dh_compass.web.services.exports import _to_csv

    content = _to_csv([{"label": "=SUM(A1:A2)"}, {"label": -12}]).decode("utf-8-sig")

    assert "'=SUM(A1:A2)" in content
    assert "-12" in content
