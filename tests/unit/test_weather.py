from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
import requests

from dh_compass.config import load_default_config
from dh_compass.demand import runtime, weather
from dh_compass.demand.heat_profiles import generate_slp_from_temperatures


@pytest.fixture
def config(tmp_path):
    base = load_default_config()
    return replace(base, paths=base.paths.with_overrides({"cache_root": tmp_path / "cache"}))


def test_weather_is_cached_and_available_offline(config, mocked_weather, monkeypatch):
    downloaded = weather.load_weather(config)
    assert len(downloaded.data) == 8760
    assert len(mocked_weather) == 1
    assert mocked_weather[0]["latitude"] == round(sum(config.scenario.bbox[1::2]) / 2, 6)
    assert downloaded.provenance["attribution"]
    monkeypatch.setattr(weather, "_fetch_response", lambda *_: pytest.fail("offline cache fetched"))
    cached = weather.load_weather(config)
    pd.testing.assert_frame_equal(cached.data, downloaded.data)
    assert cached.provenance == downloaded.provenance


def test_location_and_year_have_separate_caches(config, mocked_weather):
    other = replace(
        config, scenario=replace(config.scenario, bbox=(8.558049, 51.389164, 8.572984, 51.396903))
    )
    leap = replace(config, demand=replace(config.demand, slp_year=2024))
    for selected in (config, other, leap):
        weather.load_weather(selected)
    assert len(mocked_weather) == 3
    assert len({weather.weather_cache_path(c) for c in (config, other, leap)}) == 3
    assert len(weather.read_weather_cache(leap).data) == 8784
    assert weather.weather_request(other)["latitude"] == 51.393034


def test_corrupt_cache_is_reacquired_and_forced_refresh_works(config, mocked_weather):
    weather.load_weather(config)
    path = weather.weather_cache_path(config)
    document = json.loads(path.read_text())
    document["response"]["hourly"]["temperature_2m"][0] = 99
    path.write_text(json.dumps(document))
    with pytest.raises(weather.WeatherError, match="checksum"):
        weather.read_weather_cache(config)
    weather.load_weather(config)
    weather.load_weather(config, force_refresh=True)
    assert len(mocked_weather) == 3
    assert not list(path.parent.glob("*.tmp"))


def test_wrong_location_cache_is_not_used(config, mocked_weather):
    weather.load_weather(config)
    other = replace(config, scenario=replace(config.scenario, bbox=(7, 50, 8, 51)))
    path = weather.weather_cache_path(other)
    path.write_bytes(weather.weather_cache_path(config).read_bytes())
    with pytest.raises(weather.WeatherError, match="another location"):
        weather.read_weather_cache(other)
    weather.load_weather(other)
    assert len(mocked_weather) == 2


@pytest.mark.parametrize("problem", ["missing", "duplicate", "nan", "null", "kelvin", "offset"])
def test_invalid_provider_data_is_never_cached(config, mocked_weather, monkeypatch, problem):
    fetch = weather._fetch_response

    def corrupt(request):
        response = fetch(request)
        if problem == "missing":
            response["hourly"]["time"].pop()
        elif problem == "duplicate":
            response["hourly"]["time"][1] = response["hourly"]["time"][0]
        elif problem == "nan":
            response["hourly"]["temperature_2m"][0] = float("nan")
        elif problem == "null":
            response["hourly"]["temperature_2m"][0] = None
        elif problem == "kelvin":
            response["hourly_units"]["temperature_2m"] = "K"
        else:
            response["utc_offset_seconds"] = 3600
        return response

    monkeypatch.setattr(weather, "_fetch_response", corrupt)
    with pytest.raises(weather.WeatherError):
        weather.load_weather(config)
    assert not weather.weather_cache_path(config).exists()


def test_transport_uses_json_api_with_bounded_retries(config, monkeypatch):
    captured = {}

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def mount(self, prefix, adapter):
            captured["retries"] = adapter.max_retries

        def get(self, url, **kwargs):
            captured.update(url=url, **kwargs)
            raise requests.ConnectionError("offline")

    monkeypatch.setattr(weather.requests, "Session", Session)
    with pytest.raises(weather.WeatherError, match="internet connection"):
        weather.load_weather(config)
    assert captured["url"] == weather.ENDPOINT
    assert captured["params"]["models"] == "era5_land"
    assert captured["params"]["timezone"] == "UTC"
    assert "apikey" not in captured["params"]
    assert captured["timeout"] == (10, 30)
    assert captured["retries"].total == 2


@pytest.mark.parametrize("year", [1949, 2100])
def test_unavailable_weather_year_is_clear(config, year):
    config = replace(config, demand=replace(config.demand, slp_year=year))
    with pytest.raises(weather.WeatherError, match="completed calendar year"):
        weather.weather_request(config)


def test_runtime_uses_weather_and_calendar_factors(config, mocked_weather, monkeypatch, tmp_path):
    times = pd.date_range("2001-01-01", "2002-01-01", freq="h", inclusive="left")
    reference = pd.DataFrame({
        "Datum": times - pd.Timedelta(milliseconds=2), "temperature": [-90.0] * len(times),
        "sh_to_wh_ratio": times.hour / 24,
    })
    template = tmp_path / "reference.xlsx"
    template.touch()
    config = replace(
        config, demand=replace(config.demand, slp_year=2024),
        paths=config.paths.with_overrides({"historical_timeseries": template}),
    )
    monkeypatch.setattr(runtime, "read_ts_data", lambda *_: (reference, len(reference), 365))
    series = runtime.load_time_series(config.paths, config)
    assert series.length == 8784
    assert (series.data["temperature"] == 5).all()
    assert series.data.attrs["weather"]["weather_year"] == 2024
    local = series.timestamps.dt.tz_convert("Europe/Berlin")
    np.testing.assert_allclose(series.data["sh_to_wh_ratio"], local.dt.hour / 24)
    assert len(mocked_weather) == 1


def test_profiles_and_cop_share_local_temperatures(config, mocked_weather, monkeypatch, tmp_path):
    # Exercise the runtime without relying on provider workbooks in the checkout.
    # These independent fixture values are test inputs, not replacement defaults.
    from dh_compass.demand import heat_profiles

    calendar_path = tmp_path / "calendar.xlsx"
    calendar_path.touch()
    config = replace(config, paths=config.paths.with_overrides({"historical_timeseries": calendar_path}))
    dates = pd.date_range("2022-01-01", "2023-01-01", freq="h", inclusive="left")
    reference = pd.DataFrame({"Datum": dates, "sh_to_wh_ratio": 0.8})
    monkeypatch.setattr(runtime, "read_ts_data", lambda *_: (reference, len(reference), 365))
    parameters = pd.DataFrame([
        {"category": category, "characteristics": "03", "A": 0, "B": -30,
         "C": 2, "D": 1, "m_H": 0, "b_H": 0, "m_w": 0, "b_w": 0}
        for category in ("HEF", "HMF")
    ])
    factors = pd.DataFrame([
        {"category": category, **{day: 1.0 for day in range(1, 8)}}
        for category in ("HEF", "HMF")
    ])
    monkeypatch.setattr(heat_profiles, "_load_slp_excel", lambda *_: (parameters, factors))
    series = runtime.load_time_series(config.paths, config)
    subgraph = runtime.build_subgraph_profile_generator(
        config.paths, config, temperature_data=series.data
    )(100)
    building = runtime.build_building_profile_generator(
        config.paths, config, temperature_data=series.data
    )(10)
    assert subgraph["datetime"].equals(series.timestamps)
    assert subgraph["load"].sum() == pytest.approx(100000)
    assert building.sum() == pytest.approx(10000)
    inputs = runtime.build_technology_inputs(config.paths, config, series)
    warmed = replace(series, data=series.data.assign(temperature=15.0))
    warm_inputs = runtime.build_technology_inputs(config.paths, config, warmed)
    assert not np.array_equal(inputs.cop_central, warm_inputs.cop_central)
    assert len(mocked_weather) == 1


def test_profile_uses_german_calendar_and_preserves_utc(monkeypatch):
    from dh_compass.demand import heat_profiles

    parameters = pd.DataFrame([{
        "category": "HEF", "characteristics": "03",
        "A": 0, "B": -30, "C": 2, "D": 1,
        "m_H": 0, "b_H": 0, "m_w": 0, "b_w": 0,
    }])
    factors = pd.DataFrame([{"category": "HEF", **{i: i for i in range(1, 8)}}])
    monkeypatch.setattr(heat_profiles, "_load_slp_excel", lambda *_: (parameters, factors))
    # Monday 01:00 local versus Tuesday 01:00 local: both outside holidays.
    data = pd.DataFrame({
        "datetime": pd.to_datetime(["2022-10-09T23:00Z", "2022-10-10T23:00Z"]),
        "temperature": [5.0, 5.0],
    })
    result = generate_slp_from_temperatures(2022, "HEF", "03", 300, data)
    assert result["datetime"].equals(data["datetime"])
    assert result["load"].tolist() == pytest.approx([100, 200])
