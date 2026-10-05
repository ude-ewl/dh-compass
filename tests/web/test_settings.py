from pathlib import Path

import pytest

from dh_compass.web.settings import WebSettings


def test_settings_resolve_paths_against_explicit_project_root(tmp_path: Path) -> None:
    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=Path("metadata/web.sqlite3"),
        output_root=Path("outputs"),
        frontend_static_path=Path("frontend/dist"),
        development_cors_origins=(" http://localhost:5173 ",),
    )

    assert settings.metadata_database_path == (tmp_path / "metadata/web.sqlite3").resolve()
    assert settings.output_root == (tmp_path / "outputs").resolve()
    assert settings.frontend_static_path == (tmp_path / "frontend/dist").resolve()
    assert settings.cors_origins == ("http://localhost:5173",)
    assert settings.frontend_redesign_enabled is True


def test_environment_settings_use_explicit_values_without_current_directory(tmp_path: Path) -> None:
    settings = WebSettings.from_environment(
        {
            "DH_COMPASS_WEB_DATABASE_PATH": "db.sqlite3",
            "DH_COMPASS_WEB_OUTPUT_ROOT": "generated",
            "DH_COMPASS_WEB_WORKER_CONCURRENCY": "3",
            "DH_COMPASS_WEB_CORS_ORIGINS": "http://localhost:5173,http://localhost:4173",
            "DH_COMPASS_WEB_FRONTEND_REDESIGN": "true",
        },
        project_root=tmp_path,
    )

    assert settings.metadata_database_path == (tmp_path / "db.sqlite3").resolve()
    assert settings.output_root == (tmp_path / "generated").resolve()
    assert settings.worker_concurrency == 3
    assert settings.development_cors_origins == (
        "http://localhost:5173",
        "http://localhost:4173",
    )
    assert settings.frontend_redesign_enabled is True


def test_frontend_redesign_can_be_explicitly_disabled_for_rollback(
    tmp_path: Path,
) -> None:
    settings = WebSettings.from_environment(
        {"DH_COMPASS_WEB_FRONTEND_REDESIGN": "false"},
        project_root=tmp_path,
    )

    assert settings.frontend_redesign_enabled is False


def test_invalid_worker_concurrency_is_rejected() -> None:
    with pytest.raises(ValueError, match="worker_concurrency"):
        WebSettings(worker_concurrency=0)
