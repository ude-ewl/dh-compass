from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from dh_compass.web.schemas.base import ValidationIssue
from dh_compass.web.services.configuration import ConfigurationAdapter
from dh_compass.web.services.data_readiness import (
    DataReadinessService,
    DatasetDefinition,
)


class _Adapter:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root


def test_new_nrw_building_aliases_pass_browser_preflight(tmp_path, monkeypatch):
    import pyogrio

    path = tmp_path / "buildings.gdb"
    path.mkdir()
    monkeypatch.setattr(pyogrio, "read_info", lambda *args, **kwargs: {
        "fields": ["beheizt", "RW_WW", "Nutzflaeche"], "geometry_name": "SHAPE",
        "crs": "EPSG:25832", "total_bounds": [280000, 5570000, 531000, 5830000],
        "features": 12710308, "layer_name": "Raumwaermebedarf_ist",
    })
    service = DataReadinessService(_Adapter(tmp_path))
    definition = DatasetDefinition(
        id="buildings", label="Buildings", description="NRW heat demand", path=path,
        required=True, kind="geospatial", layer="Raumwaermebedarf_ist",
        columns=("Shape", "beheizt", "RW_WW", "NF"),
    )

    descriptor = service._validate_definition(definition, [8.795, 52.195, 8.8, 52.2], None)

    assert descriptor.status == "ready"
    assert descriptor.issues == []


def test_legacy_bad_oeynhausen_building_column_is_migrated(tmp_path: Path) -> None:
    adapter = ConfigurationAdapter(tmp_path)
    document = adapter.defaults
    document["scenario"]["building_columns"] = ["Shape", "citygml_fu", "beheizt"]

    config = adapter.to_app_config(document)

    assert config.scenario.building_columns == ("Shape", "citygml_function", "beheizt")


def test_missing_refreshable_dataset_explains_when_refresh_is_unavailable(tmp_path: Path) -> None:
    service = DataReadinessService(_Adapter(tmp_path), refreshers={})
    definition = DatasetDefinition(
        id="street_network",
        label="Street network cache",
        description="Managed network cache.",
        path=None,
        required=True,
        refreshable=True,
    )
    missing = ValidationIssue(
        severity="error",
        code="DATASET_MISSING",
        path="street_network",
        message="Street network cache could not be found.",
        remediation="Use the permitted refresh action or configure the managed dataset path.",
    )

    descriptor = service._descriptor(  # noqa: SLF001 - validates API-facing wording
        definition,
        "missing",
        None,
        [missing],
        datetime.now(timezone.utc),
    )

    assert descriptor.actions[0].allowed is False
    assert descriptor.issues[0].remediation == (
        "Automatic refresh is not configured. Configure a managed refresh provider "
        "or supply the cache manually."
    )


def test_weather_readiness_tracks_selected_area_and_validates_contents(tmp_path, mocked_weather):
    from dh_compass.demand.weather import load_weather

    adapter = ConfigurationAdapter(tmp_path)
    service = DataReadinessService(adapter, refreshers={"weather": object()})
    document = adapter.defaults
    scenario = {"revision": {"document": document}}
    config = adapter.to_app_config(document)
    assert service.validate_one(scenario, "weather").status == "missing"
    load_weather(config)
    descriptor = service.validate_one(scenario, "weather")
    assert descriptor.status == "ready"
    assert descriptor.format == "Open-Meteo JSON"
    assert descriptor.metadata["hours"] == 8760
    assert descriptor.metadata["model"] == "era5_land"
    definition = next(item for item in service.definitions(scenario) if item.id == "weather")
    definition.path.write_text("{}")
    assert service.validate_one(scenario, "weather").status == "invalid"
    document["scenario"]["bbox"] = [7, 50, 8, 51]
    assert service.validate_one(scenario, "weather").status == "missing"


def test_web_registers_weather_refresh_for_selected_area(tmp_path, mocked_weather):
    from dh_compass.web.app import _weather_refresher
    from dh_compass.web.settings import WebSettings

    adapter = ConfigurationAdapter(tmp_path)
    document = adapter.defaults
    document["scenario"]["bbox"] = [8.558049, 51.389164, 8.572984, 51.396903]
    refresh = _weather_refresher(WebSettings(project_root=tmp_path))
    scenario = {"revision": {"document": document}}
    refresh(scenario=scenario, dataset=None, force=False)
    refresh(scenario=scenario, dataset=None, force=False)
    assert len(mocked_weather) == 1
    assert mocked_weather[0]["latitude"] == 51.393034
    refresh(scenario=scenario, dataset=None, force=True)
    assert len(mocked_weather) == 2


def test_calculation_preflight_automatically_prepares_weather(tmp_path, mocked_weather):
    from dh_compass.web.jobs.calculation import CalculationJobManager

    adapter = ConfigurationAdapter(tmp_path)
    document = adapter.defaults
    scenario = {"revision": {"document": document}}
    service = DataReadinessService(adapter)

    def refresh(**kwargs):
        from dh_compass.demand.weather import load_weather
        load_weather(adapter.to_app_config(document))

    blocking = service.validate_one(scenario, "weather").issues
    assert CalculationJobManager._refresh_missing_managed_caches(
        service, scenario, blocking, {"weather": refresh}
    )
    assert service.validate_one(scenario, "weather").status == "ready"


def test_preview_allows_automatic_weather_but_still_blocks_missing_user_data():
    from dh_compass.web.api.previews import _preview_blocking_issues

    weather = ValidationIssue(
        severity="error", code="DATASET_MISSING", path="weather", message="Missing weather."
    )
    buildings = ValidationIssue(
        severity="error", code="DATASET_MISSING", path="buildings", message="Missing buildings."
    )
    refreshers = {"weather": lambda **_: None}
    assert _preview_blocking_issues([weather], refreshers) == []
    assert _preview_blocking_issues([weather, buildings], refreshers) == [buildings]
    assert _preview_blocking_issues([weather], {}) == [weather]


def test_missing_slp_parameters_block_input_readiness(tmp_path: Path) -> None:
    adapter = ConfigurationAdapter(tmp_path)
    scenario = {"revision": {"document": adapter.defaults}}
    service = DataReadinessService(adapter)

    descriptors, blocking, ready = service.readiness(scenario, dataset_ids=["slp_parameters"])

    assert not ready
    assert descriptors[0].status == "missing"
    assert [(issue.path, issue.code) for issue in blocking] == [
        ("slp_parameters", "DATASET_MISSING")
    ]


@pytest.mark.parametrize("include_weekday_factors", [False, True])
def test_slp_readiness_requires_both_runtime_sheets(
    tmp_path: Path, include_weekday_factors: bool
) -> None:
    import pandas as pd

    adapter = ConfigurationAdapter(tmp_path)
    document = {**adapter.defaults, "paths": {
        **adapter.defaults.get("paths", {}), "slp_parameters": "data/reference/test-slp.xlsx",
    }}
    scenario = {"revision": {"document": document}}
    config = adapter.to_app_config(document)
    path = config.paths.slp_parameters
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path) as workbook:
        pd.DataFrame([{
            "category": category, "Sigmoid_SigLinDe": "0", "ausprägung": "3",
            "A": 1, "B": -20, "C": 2, "D": 0.1,
            "m_H": 0, "b_H": 0, "m_w": 0, "b_w": 0,
        } for category in ("HEF", "HMF")]).to_excel(workbook, sheet_name="Parameter", index=False)
        if include_weekday_factors:
            pd.DataFrame([{"category": category, **{day: 1 for day in range(1, 8)}}
                          for category in ("HEF", "HMF")]).to_excel(
                workbook, sheet_name="Tagesfaktoren", index=False
            )

    descriptor = DataReadinessService(adapter).validate_one(scenario, "slp_parameters")

    assert descriptor.status == ("ready" if include_weekday_factors else "invalid")
    if not include_weekday_factors:
        assert descriptor.issues[0].code == "DATASET_SCHEMA_INVALID"
        assert "Tagesfaktoren" in descriptor.issues[0].message


@pytest.mark.parametrize(
    ("resource_id", "bounds"),
    [
        ("biomass", (-2824432.1198, -3076239.8068, 10026108.834, 5307233.8005)),
        ("wwtp_heat_pump", (-2683096.6583, -3075104.9262, 10024451.4615, 6208328.4402)),
    ],
)
@pytest.mark.parametrize(
    "area_bbox",
    [
        [8.558049, 51.389164, 8.572984, 51.396903],  # Brilon
        [8.744431, 52.170773, 8.849831, 52.236526],  # Bad Oeynhausen
        [6.70, 51.35, 6.85, 51.50],  # Duisburg
    ],
)
def test_european_resource_extent_covers_nrw(
    tmp_path, monkeypatch, resource_id, bounds, area_bbox
):
    import pyogrio

    path = tmp_path / "resource.gpkg"
    path.touch()
    # Real metadata extents include overseas territories. Their projected
    # diagonals do not bound the latitudes reached along the rectangle edges.
    monkeypatch.setattr(
        pyogrio,
        "read_info",
        lambda *args, **kwargs: {
            "crs": "EPSG:3035",
            "total_bounds": bounds,
            "features": 236,
            "geometry_type": "MultiPolygon",
        },
    )
    service = DataReadinessService(_Adapter(tmp_path))
    definition = DatasetDefinition(
        id=resource_id,
        label="Resource potential",
        description="Location-dependent potential.",
        path=path,
        required=True,
        kind="resource",
    )

    descriptor = service._validate_definition(definition, area_bbox, None)

    assert descriptor.status == "ready"
    assert descriptor.crs == "EPSG:3035"
    assert descriptor.extent[1] < area_bbox[1]
    assert descriptor.extent[3] > area_bbox[3]
    assert descriptor.issues == []


def test_resource_outside_area_still_warns(tmp_path, monkeypatch):
    import pyogrio

    path = tmp_path / "resource.gpkg"
    path.touch()
    monkeypatch.setattr(
        pyogrio,
        "read_info",
        lambda *args, **kwargs: {
            "crs": "EPSG:3035",
            "total_bounds": (4029902.95, 3021802.15, 4285928.55, 3217821.75),
        },
    )
    service = DataReadinessService(_Adapter(tmp_path))
    definition = DatasetDefinition(
        id="geothermal",
        label="Geothermal potential",
        description="Location-dependent potential.",
        path=path,
        required=True,
        kind="resource",
    )

    descriptor = service._validate_definition(definition, [-6.5, 53.2, -6.1, 53.5], None)

    assert descriptor.status == "ready"
    assert [issue.code for issue in descriptor.issues] == ["RESOURCE_OUTSIDE_STUDY_AREA"]


@pytest.mark.parametrize("crs", ["EPSG:4326", "EPSG:3035"])
@pytest.mark.parametrize(
    "bounds",
    [
        None,
        (1, 2, 3),
        ("invalid", 2, 3, 4),
        (float("nan"), 2, 3, 4),
        (1, 2, float("inf"), 4),
    ],
)
def test_invalid_extent_is_not_reported_as_coverage(bounds, crs):
    assert DataReadinessService._transform_bounds(bounds, crs) is None


def test_wgs84_extent_preserves_coordinate_order():
    assert DataReadinessService._transform_bounds((6, 50, 9, 53), "EPSG:4326") == [6, 50, 9, 53]
