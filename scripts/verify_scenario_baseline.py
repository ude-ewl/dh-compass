"""Compare stable aggregates from a completed scenario run with its baseline."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path


def stable_aggregates(full_results: Mapping[str, object]) -> dict[str, object]:
    """Extract deterministic planning aggregates from the public result schema."""

    combined = full_results["combined_graph"]
    if not isinstance(combined, Mapping):
        raise ValueError("Baseline verification requires at least one connected subgraph")

    subgraphs = full_results["subgraphs"]
    if not isinstance(subgraphs, Sequence):
        raise ValueError("full_results.subgraphs must be a list")

    alternatives: list[dict[str, object]] = []
    decentralized_total = 0.0
    for subgraph in subgraphs:
        if not isinstance(subgraph, Mapping):
            raise ValueError("full_results.subgraphs entries must be objects")
        alternative_key = (
            "decentral_alternative"
            if subgraph["is_connected"]
            else "decentral_supply"
        )
        alternative = subgraph.get(alternative_key, {})
        if not isinstance(alternative, Mapping):
            raise ValueError(f"{alternative_key} must be an object")
        decentralized_cost = float(alternative.get("total_annualized_cost_eur", 0.0))
        decentralized_total += decentralized_cost
        central = subgraph.get("central_cumulative_supply", {})
        if not isinstance(central, Mapping):
            central = {}
        alternatives.append(
            {
                "subgraph_id": subgraph["subgraph_id"],
                "is_connected": subgraph["is_connected"],
                "central_cost_annualized_eur": central.get("cost_annualized_eur"),
                "decentral_cost_annualized_eur": decentralized_cost,
            }
        )

    cost = combined["cost"]
    if not isinstance(cost, Mapping):
        raise ValueError("combined_graph.cost must be an object")
    grid_breakdown = cost["grid_breakdown"]
    if not isinstance(grid_breakdown, Mapping):
        raise ValueError("combined_graph.cost.grid_breakdown must be an object")

    return {
        "summary": full_results["summary"],
        "combined_graph": {
            "connected_subgraph_ids": combined["connected_subgraph_ids"],
            "annual_heat_demand_mwh": combined["annual_heat_demand_mwh"],
            "total_network_length_m": combined["total_network_length_m"],
            "total_heat_production_mwh": combined["total_heat_production_mwh"],
            "supply": combined["supply"],
            "storage": combined["storage"],
            "cost": {
                "total_annualized_eur": cost["total_annualized_eur"],
                # The central model objective excludes network annualization;
                # it is the supply component of the reported total.
                "central_model_objective_eur": cost["supply_annualized_eur"],
                "supply_annualized_eur": cost["supply_annualized_eur"],
                "grid_annualized_eur": cost["grid_annualized_eur"],
                "supply_share_pct": cost["supply_share_pct"],
                "grid_share_pct": cost["grid_share_pct"],
                "grid_breakdown": dict(grid_breakdown),
            },
        },
        "decentralized_total_annualized_eur": round(decentralized_total, 2),
        "subgraphs": alternatives,
    }


def compare(
    actual: object,
    expected: object,
    *,
    absolute_tolerance: float,
    path: str = "$",
) -> list[str]:
    """Return clear structural or numerical baseline differences."""

    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return [f"{path}: expected an object, got {type(actual).__name__}"]
        differences: list[str] = []
        if set(actual) != set(expected):
            differences.append(f"{path}: keys differ ({set(actual) ^ set(expected)})")
        for key in set(actual) & set(expected):
            differences.extend(
                compare(
                    actual[key],
                    expected[key],
                    absolute_tolerance=absolute_tolerance,
                    path=f"{path}.{key}",
                )
            )
        return differences
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path}: expected a list, got {type(actual).__name__}"]
        if len(actual) != len(expected):
            return [f"{path}: expected {len(expected)} entries, got {len(actual)}"]
        return [
            difference
            for index, (actual_item, expected_item) in enumerate(zip(actual, expected))
            for difference in compare(
                actual_item,
                expected_item,
                absolute_tolerance=absolute_tolerance,
                path=f"{path}[{index}]",
            )
        ]
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            return [f"{path}: expected {expected}, got {actual!r}"]
        if not math.isclose(actual, expected, abs_tol=absolute_tolerance, rel_tol=0.0):
            return [f"{path}: expected {expected}, got {actual}"]
        return []
    return [] if actual == expected else [f"{path}: expected {expected!r}, got {actual!r}"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="Completed run's full_results.json")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("tests/fixtures/brilon_baseline.json"),
        help="Stable aggregate baseline JSON",
    )
    args = parser.parse_args()

    actual_full = json.loads(args.results.read_text(encoding="utf-8"))
    expected_document = json.loads(args.baseline.read_text(encoding="utf-8"))
    expected = {
        key: value
        for key, value in expected_document.items()
        if key not in {"scenario", "absolute_tolerance"}
    }
    actual = stable_aggregates(actual_full)
    differences = compare(
        actual,
        expected,
        absolute_tolerance=float(expected_document["absolute_tolerance"]),
    )
    if differences:
        raise SystemExit("Scenario baseline mismatch:\n- " + "\n- ".join(differences))
    print(f"Baseline verified: {args.baseline} ({args.results})")


if __name__ == "__main__":
    main()
