"""Shared test configuration; package discovery is handled by the project install."""

from collections.abc import Mapping, Sequence
from numbers import Real
from pathlib import Path

import pytest


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def mocked_weather(monkeypatch):
    """Explicit opt-in weather transport for tests; never contact the provider."""
    import pandas as pd

    from dh_compass.demand import weather

    calls = []

    def fetch(request):
        calls.append(dict(request))
        year = int(request["start_date"][:4])
        times = pd.date_range(
            f"{year}-01-01", f"{year + 1}-01-01", freq="h", inclusive="left"
        )
        return {
            "latitude": request["latitude"],
            "longitude": request["longitude"],
            "elevation": 472.0,
            "utc_offset_seconds": 0,
            "hourly_units": {"temperature_2m": "°C"},
            "hourly": {
                "time": times.strftime("%Y-%m-%dT%H:%M").tolist(),
                "temperature_2m": [5.0] * len(times),
            },
        }

    monkeypatch.setattr(weather, "_fetch_response", fetch)
    return calls


@pytest.fixture
def assert_json_characterization():
    """Compare JSON-like data while preserving schema checks and float tolerance."""

    def compare(actual, expected, path: str = "$"):
        if isinstance(expected, Mapping):
            assert isinstance(actual, Mapping), f"{path} is not an object"
            assert set(actual) == set(expected), f"{path} has different keys"
            for key, expected_value in expected.items():
                compare(actual[key], expected_value, f"{path}.{key}")
        elif isinstance(expected, Sequence) and not isinstance(expected, str):
            assert isinstance(actual, Sequence) and not isinstance(actual, str)
            assert len(actual) == len(expected), f"{path} has a different length"
            for index, expected_value in enumerate(expected):
                compare(actual[index], expected_value, f"{path}[{index}]")
        elif isinstance(expected, Real) and not isinstance(expected, bool):
            assert actual == pytest.approx(expected), f"{path} differs"
        else:
            assert actual == expected, f"{path} differs"

    return compare
