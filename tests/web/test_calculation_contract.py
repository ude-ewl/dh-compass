from __future__ import annotations

import json
from pathlib import Path

import pytest

from dh_compass.web.services.calculation_contract import (
    DEFAULT_BBOX_LIMITS,
    DEFAULT_CONFIGURATION_VERSION,
    calculation_contract,
    validate_calculation_bbox,
)


def test_valid_calculation_bbox_returns_normalized_values_and_area() -> None:
    result = validate_calculation_bbox([7.1, 51.2, 7.2, 51.3])

    assert result.valid
    assert result.bbox == (7.1, 51.2, 7.2, 51.3)
    assert result.area_km2 == pytest.approx(76.0, rel=0.05)
    assert result.issues == ()


def test_bbox_validation_reports_all_actionable_input_issues() -> None:
    result = validate_calculation_bbox([9.0, 51.5, 7.0, 51.0])

    assert not result.valid
    assert {issue.code for issue in result.issues} == {
        "BBOX_LONGITUDE_ORDER",
        "BBOX_LATITUDE_ORDER",
    }
    world = validate_calculation_bbox([181, 51, 182, 52])
    assert "BBOX_WORLD_BOUNDS" in {issue.code for issue in world.issues}


def test_bbox_validation_rejects_non_json_number_coordinates() -> None:
    strings = validate_calculation_bbox(["7.1", 51.2, 7.2, 51.3])
    boolean = validate_calculation_bbox([True, 51.2, 7.2, 51.3])

    assert {issue.code for issue in strings.issues} == {"BBOX_COORDINATES_INVALID"}
    assert {issue.code for issue in boolean.issues} == {"BBOX_COORDINATES_INVALID"}


def test_bbox_validation_enforces_nrw_and_area_limits() -> None:
    outside = validate_calculation_bbox([5.8, 50.4, 6.0, 50.6])
    too_small = validate_calculation_bbox([7.1, 51.2, 7.10001, 51.20001])
    too_large = validate_calculation_bbox([6.0, 50.5, 9.3, 52.3])

    assert "BBOX_OUTSIDE_NRW" in {issue.code for issue in outside.issues}
    assert "BBOX_TOO_SMALL" in {issue.code for issue in too_small.issues}
    assert "BBOX_TOO_LARGE" in {issue.code for issue in too_large.issues}
    assert DEFAULT_BBOX_LIMITS.max_area_km2 == 2500.0


def test_contract_exposes_server_owned_submission_rules() -> None:
    contract = calculation_contract()

    assert contract["defaults"]["configuration_version"] == DEFAULT_CONFIGURATION_VERSION
    assert contract["bbox"]["coordinate_order"] == [
        "west",
        "south",
        "east",
        "north",
    ]
    assert contract["lifecycle"]["terminal_statuses"] == [
        "completed",
        "failed",
        "cancelled",
    ]
    assert contract["command"]["idempotency_header"] == "Idempotency-Key"


def test_contract_endpoint_is_read_only_and_matches_service(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
        frontend_static_path=tmp_path / "missing-dist",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/calculations/contract")

    assert response.status_code == 200
    body = response.json()
    assert body["command"]["method"] == "POST"
    assert body["defaults"]["configuration_version"] == DEFAULT_CONFIGURATION_VERSION
    assert body["bbox"]["max_area_km2"] == 2500.0
    assert body["lifecycle"]["response"]["status"] == "queued"


def test_documented_metric_contract_is_machine_readable() -> None:
    path = Path(__file__).parents[2] / "docs" / "frontend" / "metric-contract.json"
    document = json.loads(path.read_text(encoding="utf-8"))

    assert document["version"] == "1"
    assert document["metrics"]
    for metric in document["metrics"]:
        assert metric["id"]
        assert metric["field"]
        assert metric["unit"]
        assert metric["scope"]
        assert metric["time_basis"]
        assert metric["basis"]
        assert metric["calculation_stage"]
        assert metric["provenance"]
