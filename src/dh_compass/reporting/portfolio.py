"""Portfolio normalization and presentation helpers for reporting.

The optimization layer produces :class:`ModelSolution` objects.  Reporting
accepts those domain results and keeps the legacy mapping shape at this
boundary so existing JSON and viewer consumers remain unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from numbers import Real

import pandas as pd

Portfolio = dict[str, object]


def unwrap_stored_result(stored_result: object) -> object:
    """Return the solution from a ``(cost, solution)`` optimizer record."""

    if (
        isinstance(stored_result, tuple)
        and len(stored_result) == 2
        and isinstance(stored_result[0], Real)
    ):
        return stored_result[1]
    return stored_result


def portfolio_from_solution(solution: object) -> Portfolio:
    """Return the stable portfolio mapping for a domain solution.

    Current optimization runs pass ``ModelSolution`` instances. Mappings are
    accepted for reporting integrations that already persist the JSON-shaped
    portfolio. Solver and value-frame extraction belongs exclusively to
    ``optimization.result_extraction`` and is not supported by reporting.
    """

    if solution is None:
        return {}

    to_portfolio = getattr(solution, "to_portfolio_dict", None)
    if callable(to_portfolio):
        portfolio = to_portfolio()
        return dict(portfolio) if isinstance(portfolio, Mapping) else {}

    if isinstance(solution, Mapping):
        nested = solution.get("portfolio")
        if isinstance(nested, Mapping):
            return dict(nested)
        return dict(solution)

    return {}


def portfolio_from_stored_result(stored_result: object) -> Portfolio:
    """Normalize one optimizer state entry to a portfolio mapping."""

    return portfolio_from_solution(unwrap_stored_result(stored_result))


def result_frame_from_stored_result(stored_result: object) -> pd.DataFrame | None:
    """Return the optional time-series frame from a domain solution."""

    result_frame = getattr(unwrap_stored_result(stored_result), "result_df", None)
    return result_frame if isinstance(result_frame, pd.DataFrame) else None


def portfolio_energy_key(technology: str) -> str:
    """Return the annual heat-energy field used by a technology result."""

    if technology in {"chp", "biomass_chp"}:
        return "annual_heat_energy_mwh"
    return "annual_energy_mwh"


def portfolio_energy_mwh(technology: str, technology_result: Mapping[str, object]) -> float:
    """Read a technology's annual heat output in MWh."""

    return float(technology_result.get(portfolio_energy_key(technology), 0))


def aggregate_supply_energy(
    portfolios: Iterable[tuple[Mapping[str, object], float]],
) -> dict[str, dict[str, float]]:
    """Aggregate scaled annual technology output and calculate shares.

    ``portfolios`` contains ``(portfolio, scaling_factor)`` pairs, which is
    the representation used for decentralized cluster reporting.
    """

    energy_by_technology: dict[str, float] = {}
    for portfolio, scaling_factor in portfolios:
        for technology, technology_result in portfolio.get("supply", {}).items():
            energy = portfolio_energy_mwh(technology, technology_result)
            energy_by_technology[technology] = energy_by_technology.get(technology, 0.0) + (
                energy * scaling_factor
            )

    total_energy = sum(energy_by_technology.values())
    return {
        technology: {
            "annual_energy_mwh": round(energy, 4),
            "energy_share_pct": round(energy / total_energy * 100, 2)
            if total_energy > 0
            else 0,
        }
        for technology, energy in energy_by_technology.items()
    }


__all__ = [
    "Portfolio",
    "aggregate_supply_energy",
    "portfolio_energy_key",
    "portfolio_energy_mwh",
    "portfolio_from_solution",
    "portfolio_from_stored_result",
    "result_frame_from_stored_result",
    "unwrap_stored_result",
]
