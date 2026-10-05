from __future__ import annotations

import asyncio
import json
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.skipif(
    any(find_spec(name) is None for name in ("fastapi", "pydantic", "sqlalchemy")),
    reason="web dependencies are not installed",
)


def test_startup_status_reports_compatible_frontend_and_migrations(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.settings import WebSettings

    for directory in (
        tmp_path / "data" / "reference",
        tmp_path / "data" / "external",
        tmp_path / "data" / "examples",
    ):
        directory.mkdir(parents=True)
    static = tmp_path / "frontend-dist"
    static.mkdir()
    (static / "index.html").write_text("<html></html>", encoding="utf-8")
    (static / "dh-compass-frontend.json").write_text(
        json.dumps(
            {
                "application": "dh-compass",
                "frontend_version": "0.1.0",
                "api_version": "0.1.0",
                "api_prefix": "/api/v1",
            }
        ),
        encoding="utf-8",
    )

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
        frontend_static_path=static,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/system/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ready", "degraded"}
    assert body["migration_version"] == body["expected_migration_version"] == 2
    assert body["frontend_api_version"] == "0.1.0"
    assert {item["code"] for item in body["checks"]} >= {
        "DATABASE_MIGRATIONS_CURRENT",
        "FRONTEND_VERSION_COMPATIBLE",
    }


def test_incompatible_frontend_assets_fail_web_startup(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.settings import WebSettings

    static = tmp_path / "frontend-dist"
    static.mkdir()
    (static / "index.html").write_text("<html></html>", encoding="utf-8")
    (static / "dh-compass-frontend.json").write_text(
        json.dumps({"application": "dh-compass", "api_version": "0.0.0"}),
        encoding="utf-8",
    )
    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
        frontend_static_path=static,
    )

    with pytest.raises(RuntimeError, match="startup checks failed"), TestClient(
        create_app(settings)
    ):
        pass


def test_legacy_viewer_remains_a_discoverable_compatibility_fallback(tmp_path: Path) -> None:
    from dh_compass.reporting.viewer_export import save_viewer_data
    from dh_compass.web.services.output_discovery import OutputDiscoveryService

    run = tmp_path / "outputs" / "demo" / "20240101T000000Z"
    run.mkdir(parents=True)
    save_viewer_data(
        {"iterations": [], "subgraphs": {}},
        run / "viewer_data.json",
        template_path=Path(__file__).parents[2] / "templates" / "viewer.html",
    )

    manifest = OutputDiscoveryService(tmp_path / "outputs").list_runs()[0]
    artifact = next(item for item in manifest.artifacts if item.id == "viewer_data.html")
    assert artifact.status == "available"
    assert "deprecated-compatibility-fallback" in (run / "viewer_data.html").read_text(
        encoding="utf-8"
    )


def test_web_cli_passes_explicit_bind_options_and_defers_browser_until_ready(
    tmp_path: Path,
) -> None:
    from dh_compass.cli import main

    with (
        patch("uvicorn.Config") as config,
        patch("uvicorn.Server.run", autospec=True) as run,
        patch("webbrowser.open") as open_browser,
    ):
        result = main(
            [
                "web",
                "--project-root",
                str(tmp_path),
                "--host",
                "127.0.0.1",
                "--port",
                "8123",
                "--open-browser",
            ]
        )
        server = run.call_args.args[0]

        async def mark_listener_ready(server, sockets=None) -> None:
            del sockets
            server.started = True

        with patch("uvicorn.Server.startup", new=mark_listener_ready):
            asyncio.run(server.startup())

    assert result == 0
    assert config.call_args.args[0]
    assert config.call_args.kwargs["host"] == "127.0.0.1"
    assert config.call_args.kwargs["port"] == 8123
    assert run.called
    open_browser.assert_called_once_with("http://127.0.0.1:8123/")
