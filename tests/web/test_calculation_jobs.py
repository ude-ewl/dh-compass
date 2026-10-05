from __future__ import annotations

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
