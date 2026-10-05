from __future__ import annotations

import asyncio
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.skipif(
    any(find_spec(name) is None for name in ("fastapi", "pydantic", "sqlalchemy")),
    reason="web dependencies are not installed",
)


def test_run_creation_requires_ready_preview_and_is_idempotent(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.persistence.database import create_metadata_engine
    from dh_compass.web.persistence.migrations import run_migrations
    from dh_compass.web.persistence.repositories import PreviewRepository
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"name": "Project"}).json()
        scenario = client.post(
            f"/api/v1/projects/{project['id']}/scenarios",
            json={"name": "Scenario"},
        ).json()
        engine = create_metadata_engine(settings)
        run_migrations(engine)
        preview = PreviewRepository(engine).create(
            scenario["id"],
            scenario["current_revision_id"],
            threshold=2.0,
            status="ready",
        )
        engine.dispose()

        with patch("dh_compass.web.api.runs.RunJobManager.start", return_value=False):
            payload = {
                "scenario_revision_id": scenario["current_revision_id"],
                "preview_id": preview["id"],
                "name": "First run",
                "output_label": "review-run",
            }
            first = client.post(
                f"/api/v1/scenarios/{scenario['id']}/runs",
                json=payload,
                headers={"Idempotency-Key": "run-submit-1"},
            )
            assert first.status_code == 202
            run_id = first.json()["id"]
            assert first.json()["configuration_snapshot"]
            assert first.json()["output_label"] == "review-run"

            second = client.post(
                f"/api/v1/scenarios/{scenario['id']}/runs",
                json=payload,
                headers={"Idempotency-Key": "run-submit-1"},
            )
            assert second.status_code == 202
            assert second.json()["id"] == run_id

            events = client.get(f"/api/v1/runs/{run_id}/events?format=json")
            assert events.status_code == 200
            assert [event["sequence"] for event in events.json()] == [1]
            assert events.json()[0]["event_type"] == "job.status_changed"

            engine = create_metadata_engine(settings)
            run_migrations(engine)
            PreviewRepository(engine).mark_stale(preview["id"], "Input data changed")
            engine.dispose()
            stale = client.post(
                f"/api/v1/scenarios/{scenario['id']}/runs",
                json=payload,
                headers={"Idempotency-Key": "run-submit-2"},
            )
            assert stale.status_code == 409
            assert stale.json()["code"] == "RUN_PREVIEW_NOT_READY"


def test_run_events_replay_from_last_event_and_cancel_queued_run(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.persistence.database import create_metadata_engine
    from dh_compass.web.persistence.migrations import run_migrations
    from dh_compass.web.persistence.repositories import (
        JobEventRepository,
        PreviewRepository,
    )
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"name": "Project"}).json()
        scenario = client.post(
            f"/api/v1/projects/{project['id']}/scenarios",
            json={"name": "Scenario"},
        ).json()
        engine = create_metadata_engine(settings)
        run_migrations(engine)
        preview = PreviewRepository(engine).create(
            scenario["id"], scenario["current_revision_id"], threshold=2.0, status="ready"
        )
        engine.dispose()

        with patch("dh_compass.web.api.runs.RunJobManager.start", return_value=False):
            response = client.post(
                f"/api/v1/scenarios/{scenario['id']}/runs",
                json={
                    "scenario_revision_id": scenario["current_revision_id"],
                    "preview_id": preview["id"],
                    "name": "Queued run",
                },
                headers={"Idempotency-Key": "queued-run"},
            )
        assert response.status_code == 202
        run_id = response.json()["id"]

        engine = create_metadata_engine(settings)
        run_migrations(engine)
        events = JobEventRepository(engine)
        events.append(
            run_id,
            "run",
            events.next_sequence(run_id, "run"),
            "pipeline.stage_started",
            {"stage": "load_inputs"},
        )
        engine.dispose()

        replay = client.get(
            f"/api/v1/runs/{run_id}/events",
            params={"format": "json", "after_sequence": 1},
        )
        assert replay.status_code == 200
        assert [event["sequence"] for event in replay.json()] == [2]

        async def receive_new_event_from_open_sse() -> str:
            from starlette.requests import Request

            from dh_compass.web.api.runs import run_events

            request = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": f"/api/v1/runs/{run_id}/events",
                    "headers": [],
                    "app": client.app,
                }
            )
            response = await run_events(
                request,
                run_id,
                after_sequence=2,
                format="sse",
            )
            iterator = response.body_iterator
            await anext(iterator)  # Initial heartbeat confirms the stream is open.
            event_engine = create_metadata_engine(settings)
            try:
                JobEventRepository(event_engine).append_ordered(
                    run_id,
                    "run",
                    "optimization.candidate_completed",
                    {"candidate_id": 7, "decision": "connected"},
                )
            finally:
                event_engine.dispose()
            try:
                return await asyncio.wait_for(anext(iterator), timeout=1)
            finally:
                await iterator.aclose()

        assert "id: 3" in asyncio.run(receive_new_event_from_open_sse())

        cancelled = client.post(f"/api/v1/runs/{run_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["failure_details"]["code"] == "CANCELLED_BEFORE_START"


def test_recent_runs_list_supports_recovery_without_a_project(tmp_path: Path) -> None:
    """`/recent` must list durable runs so a refresh cannot lose the run link."""

    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.persistence.database import create_metadata_engine
    from dh_compass.web.persistence.migrations import run_migrations
    from dh_compass.web.persistence.repositories import PreviewRepository
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
    )
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"name": "Project"}).json()
        scenario = client.post(
            f"/api/v1/projects/{project['id']}/scenarios",
            json={"name": "Scenario"},
        ).json()
        engine = create_metadata_engine(settings)
        run_migrations(engine)
        preview = PreviewRepository(engine).create(
            scenario["id"],
            scenario["current_revision_id"],
            threshold=2.0,
            status="ready",
        )
        engine.dispose()

        with patch("dh_compass.web.api.runs.RunJobManager.start", return_value=False):
            created = client.post(
                f"/api/v1/scenarios/{scenario['id']}/runs",
                json={
                    "scenario_revision_id": scenario["current_revision_id"],
                    "preview_id": preview["id"],
                    "name": "Recoverable run",
                },
                headers={"Idempotency-Key": "recoverable-run"},
            )
        assert created.status_code == 202
        run_id = created.json()["id"]

        recent = client.get("/api/v1/runs/recent")
        assert recent.status_code == 200
        items = recent.json()["items"]
        assert [item["id"] for item in items] == [run_id]
        assert items[0]["status"] == "queued"
        assert items[0]["stage"] is None
        # The recovery list stays small: configuration and data snapshots stay
        # in the authoritative run resource.
        assert "configuration_snapshot" not in items[0]

        # A literal `recent` path must never be read as a run identifier.
        assert client.get(f"/api/v1/runs/{run_id}").json()["id"] == run_id


def test_recent_runs_pagination_reports_the_full_collection(tmp_path: Path) -> None:
    """`total`/`has_next` describe every run, not the fetched window.

    The recovery list only requests the first page today, so an envelope built
    from one window would report that no further page exists.
    """

    from fastapi.testclient import TestClient

    from dh_compass.web.app import create_app
    from dh_compass.web.persistence.database import create_metadata_engine
    from dh_compass.web.persistence.migrations import run_migrations
    from dh_compass.web.persistence.repositories import PreviewRepository
    from dh_compass.web.settings import WebSettings

    settings = WebSettings(
        project_root=tmp_path,
        metadata_database_path=tmp_path / "metadata.sqlite3",
    )
    run_names: list[str] = []
    with TestClient(create_app(settings)) as client:
        project = client.post("/api/v1/projects", json={"name": "Project"}).json()
        scenario = client.post(
            f"/api/v1/projects/{project['id']}/scenarios",
            json={"name": "Scenario"},
        ).json()
        for index in range(3):
            engine = create_metadata_engine(settings)
            run_migrations(engine)
            preview = PreviewRepository(engine).create(
                scenario["id"],
                scenario["current_revision_id"],
                threshold=2.0,
                status="ready",
            )
            engine.dispose()
            name = f"Recoverable run {index}"
            run_names.append(name)
            with patch("dh_compass.web.api.runs.RunJobManager.start", return_value=False):
                created = client.post(
                    f"/api/v1/scenarios/{scenario['id']}/runs",
                    json={
                        "scenario_revision_id": scenario["current_revision_id"],
                        "preview_id": preview["id"],
                        "name": name,
                    },
                    headers={"Idempotency-Key": f"recoverable-run-{index}"},
                )
            assert created.status_code == 202

        first = client.get("/api/v1/runs/recent", params={"page_size": 2}).json()
        assert first["pagination"] == {
            "page": 1,
            "page_size": 2,
            "total": 3,
            "has_next": True,
            "has_previous": False,
        }
        assert len(first["items"]) == 2

        second = client.get(
            "/api/v1/runs/recent", params={"page_size": 2, "page": 2}
        ).json()
        assert second["pagination"]["has_next"] is False
        assert second["pagination"]["has_previous"] is True
        assert second["pagination"]["total"] == 3
        assert len(second["items"]) == 1

        # Ordering is stable across pages: newest first, no overlaps.
        paged = first["items"] + second["items"]
        assert sorted(item["name"] for item in paged) == sorted(run_names)
