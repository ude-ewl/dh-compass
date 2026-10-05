"""Milestone 2 project and scenario API characterization tests."""

from __future__ import annotations

import copy
from importlib.util import find_spec
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    any(find_spec(name) is None for name in ("fastapi", "pydantic", "sqlalchemy")),
    reason="web dependencies are not installed",
)


def _client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
    )
    return TestClient(create_app(settings))


def _create_scenario(client) -> tuple[str, dict[str, object]]:
    project = client.post("/api/v1/projects", json={"name": "Test project"})
    assert project.status_code == 201
    project_id = project.json()["id"]
    scenario = client.post(
        f"/api/v1/projects/{project_id}/scenarios",
        json={"name": "Test scenario", "description": "Original description"},
    )
    assert scenario.status_code == 201
    return project_id, scenario.json()


def test_metadata_edits_create_revisions_detect_conflicts_and_can_clear_description(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        _, scenario = _create_scenario(client)
        scenario_id = scenario["id"]
        revision_id = scenario["current_revision_id"]

        first = client.patch(
            f"/api/v1/scenarios/{scenario_id}",
            json={
                "expected_revision_id": revision_id,
                "name": "Renamed scenario",
                "description": "Changed description",
            },
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["current_revision_id"] != revision_id
        assert first_body["revision_number"] == 2

        stale = client.patch(
            f"/api/v1/scenarios/{scenario_id}",
            json={"expected_revision_id": revision_id, "description": "Lost update"},
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "SCENARIO_REVISION_CONFLICT"

        cleared = client.patch(
            f"/api/v1/scenarios/{scenario_id}",
            json={
                "expected_revision_id": first_body["current_revision_id"],
                "description": None,
            },
        )
        assert cleared.status_code == 200
        assert cleared.json()["description"] is None
        assert cleared.json()["revision_number"] == 3


def test_configuration_revisions_are_immutable_and_use_optimistic_concurrency(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        _, scenario = _create_scenario(client)
        scenario_id = scenario["id"]
        original = client.get(f"/api/v1/scenarios/{scenario_id}/config").json()
        changed_document = copy.deepcopy(original["document"])
        changed_document["network"]["linear_heat_density_threshold"] = 42

        updated = client.put(
            f"/api/v1/scenarios/{scenario_id}/config",
            json={
                "expected_revision_id": original["revision_id"],
                "document": changed_document,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["revision"]["revision_number"] == 2

        stale = client.put(
            f"/api/v1/scenarios/{scenario_id}/config",
            json={
                "expected_revision_id": original["revision_id"],
                "document": changed_document,
            },
        )
        assert stale.status_code == 409

        revisions = client.get(f"/api/v1/scenarios/{scenario_id}/revisions")
        assert revisions.status_code == 200
        documents = {item["revision_number"]: item["document"] for item in revisions.json()["items"]}
        assert documents[1] == original["document"]
        assert documents[2]["network"]["linear_heat_density_threshold"] == 42


def test_scenario_archive_duplicate_and_toml_round_trip(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id, scenario = _create_scenario(client)
        scenario_id = scenario["id"]

        exported = client.get(f"/api/v1/scenarios/{scenario_id}/config.toml")
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("application/toml")

        imported = client.post(
            "/api/v1/scenarios/import",
            json={"project_id": project_id, "name": "Imported", "toml": exported.text},
        )
        assert imported.status_code == 201
        assert imported.json()["revision_number"] == 1

        duplicate = client.post(f"/api/v1/scenarios/{scenario_id}/duplicate", json={})
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] != scenario_id
        assert duplicate.json()["revision"]["document"] == scenario["revision"]["document"]

        archived = client.patch(
            f"/api/v1/scenarios/{scenario_id}",
            json={"expected_revision_id": scenario["current_revision_id"], "archived": True},
        )
        assert archived.status_code == 200
        assert archived.json()["archived"] is True

        visible = client.get(f"/api/v1/projects/{project_id}/scenarios")
        assert visible.status_code == 200
        assert scenario_id not in {item["id"] for item in visible.json()["items"]}


def test_expert_schema_covers_fields_and_exposes_revision_comparisons(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _, scenario = _create_scenario(client)
        scenario_id = scenario["id"]

        schema = client.get(
            "/api/v1/configuration/schema",
            params={"scenario_id": scenario_id},
        )
        assert schema.status_code == 200
        fields = {field["key"]: field for field in schema.json()["fields"]}
        assert "network.linear_heat_density_threshold" in fields
        assert "economics.cost_structures.chp.300" in fields
        assert "technologies.boiler_central.0.efficiency" in fields
        assert fields["network.linear_heat_density_threshold"]["expert_only"] is False
        assert fields["economics.cost_structures.chp.300"]["expert_only"] is True
        assert fields["economics.cost_structures.chp.300"]["group"] == "cost_curves"
        assert fields["paths.output_root"]["editable"] is False

        config = client.get(f"/api/v1/scenarios/{scenario_id}/config").json()
        changed = copy.deepcopy(config["document"])
        changed["economics"]["interest_rate"] = 0.08
        updated = client.put(
            f"/api/v1/scenarios/{scenario_id}/config",
            json={
                "expected_revision_id": config["revision_id"],
                "document": changed,
            },
        )
        assert updated.status_code == 200
        assert "economics.interest_rate" in updated.json()["changed_from_default"]
        assert "economics.interest_rate" in updated.json()["changed_from_parent"]


def test_expert_validation_is_atomic_and_classifies_downstream_effects(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        _, scenario = _create_scenario(client)
        scenario_id = scenario["id"]
        config = client.get(f"/api/v1/scenarios/{scenario_id}/config").json()

        invalid = client.post(
            f"/api/v1/scenarios/{scenario_id}/validate",
            json={"toml": "[network]\nlinear_heat_density_threshold = -1"},
        )
        assert invalid.status_code == 200
        assert invalid.json()["valid"] is False
        assert invalid.json()["field_errors"][0]["path"] == (
            "network.linear_heat_density_threshold"
        )
        assert client.get(f"/api/v1/scenarios/{scenario_id}/config").json()[
            "revision_id"
        ] == config["revision_id"]

        valid = client.post(
            f"/api/v1/scenarios/{scenario_id}/validate",
            json={"toml": "[economics]\ninterest_rate = 0.08"},
        )
        assert valid.status_code == 200
        body = valid.json()
        assert body["valid"] is True
        assert body["invalidation"]["effect"] == "new_run_required"
        assert body["invalidation"]["new_run_required"] is True
        assert body["merged_toml"]


def test_expert_schema_includes_dynamic_cost_and_technology_entries(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        _, scenario = _create_scenario(client)
        scenario_id = scenario["id"]
        config = client.get(f"/api/v1/scenarios/{scenario_id}/config").json()
        changed = copy.deepcopy(config["document"])
        changed["economics"]["cost_structures"]["chp"]["350"] = 999
        changed["technologies"]["boiler_central"]["1"] = {
            "efficiency": 0.9,
            "on_off": 1,
        }

        updated = client.put(
            f"/api/v1/scenarios/{scenario_id}/config",
            json={
                "expected_revision_id": config["revision_id"],
                "document": changed,
                "replace": True,
            },
        )
        assert updated.status_code == 200

        schema = client.get(
            "/api/v1/configuration/schema",
            params={"scenario_id": scenario_id},
        )
        fields = {field["key"]: field for field in schema.json()["fields"]}
        assert fields["economics.cost_structures.chp.350"]["changed_from_default"] is True
        assert fields["economics.cost_structures.chp.350"]["has_default"] is False
        assert fields["technologies.boiler_central.1.efficiency"]["value"] == 0.9
        assert fields["technologies.boiler_central.1.on_off"]["has_default"] is False


def test_replacing_a_cost_curve_can_remove_a_threshold(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _, scenario = _create_scenario(client)
        scenario_id = scenario["id"]
        config = client.get(f"/api/v1/scenarios/{scenario_id}/config").json()
        changed = copy.deepcopy(config["document"])
        curve = changed["economics"]["cost_structures"]["chp"]
        value = curve.pop("300")
        curve["350"] = value

        updated = client.put(
            f"/api/v1/scenarios/{scenario_id}/config",
            json={
                "expected_revision_id": config["revision_id"],
                "document": changed,
                "replace": True,
            },
        )
        assert updated.status_code == 200
        saved_curve = updated.json()["revision"]["document"]["economics"]["cost_structures"]["chp"]
        assert "300" not in saved_curve
        assert saved_curve["350"] == value


def test_path_policy_rejects_managed_and_workspace_escape_overrides(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _, scenario = _create_scenario(client)
        scenario_id = scenario["id"]
        for toml in (
            "[paths]\noutput_root = \"outputs\"",
            "[paths]\nbuilding_data = \"../outside.gdb\"",
            "[resources]\nbiomass_path = \"../outside.gpkg\"",
        ):
            response = client.post(
                f"/api/v1/scenarios/{scenario_id}/validate",
                json={"toml": toml},
            )
            assert response.status_code == 200
            assert response.json()["valid"] is False
            assert response.json()["field_errors"][0]["path"]


def test_import_reports_field_level_validation_errors(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        project_id, _ = _create_scenario(client)
        response = client.post(
            "/api/v1/scenarios/import",
            json={"project_id": project_id, "toml": "[network]\nlinear_heat_density_threshold = -1"},
        )
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "SCENARIO_VALIDATION_FAILED"
        assert body["field_errors"]
        assert body["field_errors"][0]["path"]
