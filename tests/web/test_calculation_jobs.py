from __future__ import annotations

import pytest

from dh_compass.web.jobs.calculation import CalculationJobManager
from dh_compass.web.schemas.base import ValidationIssue


class _Readiness:
    def __init__(self) -> None:
        self.refresh_calls: list[dict[str, object]] = []

    def refresh(self, scenario, dataset_id, *, provider):  # noqa: ANN001 - test double
        self.refresh_calls.append(
            {
                "scenario": scenario,
                "dataset_id": dataset_id,
                "provider": provider,
            }
        )


class _RetryingReadiness(_Readiness):
    def __init__(self, issue: ValidationIssue) -> None:
        super().__init__()
        self.issue = issue
        self.readiness_calls = 0

    def readiness(self, scenario):  # noqa: ANN001 - test double
        self.readiness_calls += 1
        if self.readiness_calls == 1:
            return [], [self.issue], False
        return [], [], True


def test_missing_managed_street_cache_is_refreshed_before_calculation_fails() -> None:
    """A one-command calculation owns creation of its bbox-specific cache."""
    readiness = _Readiness()
    scenario = {"id": "scenario-1"}

    def refresh_street_network(**_kwargs):
        return None

    refreshed = CalculationJobManager._refresh_missing_managed_caches(
        readiness,
        scenario,
        [
            ValidationIssue(
                severity="error",
                code="DATASET_MISSING",
                path="street_network",
                message="Street network cache could not be found.",
                remediation="Refresh it.",
            )
        ],
        {"street_network": refresh_street_network},
    )

    assert refreshed is True
    assert readiness.refresh_calls == [
        {
            "scenario": scenario,
            "dataset_id": "street_network",
            "provider": refresh_street_network,
        }
    ]


def test_calculation_rechecks_readiness_after_refreshing_a_missing_managed_cache() -> None:
    issue = ValidationIssue(
        severity="error",
        code="DATASET_MISSING",
        path="street_network",
        message="Street network cache could not be found.",
        remediation="Refresh it.",
    )
    readiness = _RetryingReadiness(issue)
    scenario = {"id": "scenario-1"}

    descriptors, blocking, ready = CalculationJobManager._readiness_with_managed_refresh(
        readiness,
        scenario,
        {"street_network": lambda **_kwargs: None},
    )

    assert descriptors == []
    assert blocking == []
    assert ready is True
    assert readiness.readiness_calls == 2
    assert [call["dataset_id"] for call in readiness.refresh_calls] == ["street_network"]


def test_missing_static_input_does_not_prevent_managed_cache_preparation() -> None:
    class MixedReadiness(_Readiness):
        def readiness(self, scenario):  # noqa: ANN001 - test double
            missing = ["slp_parameters"]
            if not self.refresh_calls:
                missing = ["street_network", "slp_parameters", "weather", "weather"]
            return [], [
                ValidationIssue(
                    severity="error", code="DATASET_MISSING", path=dataset,
                    message="Missing input", remediation="Provide input",
                ) for dataset in missing
            ], False

    readiness = MixedReadiness()
    descriptors, blocking, ready = CalculationJobManager._readiness_with_managed_refresh(
        readiness, {},
        {"street_network": lambda **_kwargs: None, "weather": lambda **_kwargs: None},
    )

    assert descriptors == []
    assert ready is False
    assert [issue.path for issue in blocking] == ["slp_parameters"]
    assert [call["dataset_id"] for call in readiness.refresh_calls] == [
        "street_network", "weather",
    ]


def test_overpass_timeout_becomes_an_actionable_input_issue() -> None:
    from requests.exceptions import ConnectTimeout

    class TimeoutReadiness(_Readiness):
        def readiness(self, scenario):
            return [], [ValidationIssue(
                severity="error", code="DATASET_MISSING", path="street_network",
                message="Street network cache could not be found.", remediation="Refresh it.",
            )], False

        def refresh(self, scenario, dataset_id, *, provider):
            provider()

    def unavailable_overpass():
        raise ConnectTimeout("Connection to overpass-api.de timed out. (connect timeout=180)")

    _, blocking, ready = CalculationJobManager._readiness_with_managed_refresh(
        TimeoutReadiness(), {}, {"street_network": unavailable_overpass},
    )
    assert not ready
    assert len(blocking) == 1
    assert blocking[0].code == "DATASET_REFRESH_FAILED"
    assert blocking[0].path == "street_network"
    assert "OpenStreetMap" in blocking[0].message
    assert "connection" in blocking[0].remediation.lower()


@pytest.mark.parametrize("order", [("street_network", "weather"), ("weather", "street_network")])
@pytest.mark.parametrize("weather_fails", [False, True])
def test_failed_street_download_does_not_skip_weather_or_report_stale_errors(order, weather_fails):
    from requests.exceptions import ConnectTimeout

    from dh_compass.demand.weather import WeatherError

    attempts = []
    available = set()

    class IndependentReadiness:
        def readiness(self, scenario):
            issues = [ValidationIssue(
                severity="error", code="DATASET_MISSING", path=dataset,
                message="Missing input", remediation="Refresh it.",
            ) for dataset in order if dataset not in available]
            return sorted(available), issues, not issues

        def refresh(self, scenario, dataset_id, *, provider):
            attempts.append(dataset_id)
            provider()
            available.add(dataset_id)

    def failed_street_download():
        raise ConnectTimeout("Connection to overpass-api.de timed out.")

    def download_weather():
        if weather_fails:
            raise WeatherError("Local weather could not be downloaded from Open-Meteo.")

    descriptors, blocking, ready = CalculationJobManager._readiness_with_managed_refresh(
        IndependentReadiness(), {}, {
            "street_network": failed_street_download, "weather": download_weather,
        },
    )
    assert attempts == list(order)
    assert descriptors == ([] if weather_fails else ["weather"])
    assert not ready
    assert [(issue.path, issue.code) for issue in blocking] == [
        (dataset, "DATASET_REFRESH_FAILED") for dataset in order
        if dataset == "street_network" or weather_fails
    ]
