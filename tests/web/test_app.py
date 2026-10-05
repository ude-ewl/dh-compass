from importlib.util import find_spec
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    any(find_spec(name) is None for name in ("fastapi", "pydantic", "sqlalchemy")),
    reason="web dependencies are not installed",
)


def _client(tmp_path: Path, *, static_path: Path | None = None):
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
        frontend_static_path=static_path,
    )
    return TestClient(create_app(settings))


def test_health_exposes_openapi_and_request_id(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/health", headers={"X-Request-ID": "test-request-7"})
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "service": "dh-compass-api",
            "version": "0.1.0",
            "request_id": "test-request-7",
        }
        assert response.headers["X-Request-ID"] == "test-request-7"

        openapi = client.get("/api/v1/openapi.json")
        assert openapi.status_code == 200
        assert "/api/v1/health" in openapi.json()["paths"]


def test_system_status_exposes_the_redesign_rollout_flag(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/system/status")

    assert response.status_code == 200
    assert response.json()["features"]["frontend_redesign"] is True


def test_web_app_registers_the_street_network_cache_refresher(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        refreshers = client.app.state.cache_refreshers
        assert callable(refreshers["street_network"])


def test_not_found_errors_use_the_normalized_shape(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/does-not-exist", headers={"X-Request-ID": "missing-9"})
        assert response.status_code == 404
        assert response.json() == {
            "code": "NOT_FOUND",
            "message": "Not Found",
            "field_errors": [],
            "details": {},
            "request_id": "missing-9",
        }


def test_validation_and_unexpected_errors_are_normalized(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
    )
    app: FastAPI = create_app(settings)

    @app.get("/api/v1/test-validation")
    async def test_validation(value: int) -> dict[str, int]:
        return {"value": value}

    @app.get("/api/v1/test-error")
    async def test_error() -> None:
        raise RuntimeError("test-only unexpected error")

    with TestClient(app, raise_server_exceptions=False) as client:
        validation = client.get("/api/v1/test-validation", headers={"X-Request-ID": "invalid-9"})
        assert validation.status_code == 422
        assert validation.json() == {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed.",
            "field_errors": [
                {
                    "path": "query.value",
                    "message": "Field required",
                    "code": "missing",
                }
            ],
            "details": {},
            "request_id": "invalid-9",
        }

        unexpected = client.get("/api/v1/test-error", headers={"X-Request-ID": "error-9"})
        assert unexpected.status_code == 500
        assert unexpected.json() == {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected server error occurred.",
            "field_errors": [],
            "details": {},
            "request_id": "error-9",
        }


def test_compiled_frontend_is_served_with_history_fallback(tmp_path: Path) -> None:
    static_path = tmp_path / "dist"
    static_path.mkdir()
    (static_path / "index.html").write_text("<html><body>shell</body></html>", encoding="utf-8")
    (static_path / "asset.txt").write_text("asset", encoding="utf-8")

    with _client(tmp_path, static_path=static_path) as client:
        assert client.get("/asset.txt").text == "asset"
        assert client.get("/projects/example").text == "<html><body>shell</body></html>"
        missing_api = client.get("/api/v1/missing")
        assert missing_api.status_code == 404
        assert missing_api.json()["code"] == "NOT_FOUND"
