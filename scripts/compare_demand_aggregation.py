import json
import sys
from pathlib import Path

import pandas as pd

FLH_THRESHOLD_PCT = 1.0


def load_edges(results_dir: Path) -> pd.DataFrame:
    with open(results_dir / "lhd_graph.geojson", encoding="utf-8") as f:
        gj = json.load(f)
    rows = [feat["properties"] for feat in gj["features"]]
    return pd.DataFrame(rows)


def load_summary(results_dir: Path) -> dict:
    with open(results_dir / "full_results.json", encoding="utf-8") as f:
        return json.load(f).get("summary", {})


def aggregate_per_subgraph(edges: pd.DataFrame) -> pd.DataFrame:
    grouped = edges.groupby("component_id")
    per_sg = grouped.apply(
        lambda g: pd.Series(
            {
                "edges": len(g),
                "length_m": g["length_m"].sum(),
                "buildings": g["building_count"].sum(),
                "annual_new_mwh": g["heat_demand_mwh"].sum(),
                "avg_lhd_old": g["linear_heat_density"].mean(),
                "avg_lhd_new": g["heat_demand_mwh"].sum() / g["length_m"].sum(),
            }
        ),
        include_groups=False,
    )
    per_sg["annual_old_mwh"] = per_sg["avg_lhd_old"] * per_sg["length_m"]
    per_sg["delta_mwh"] = per_sg["annual_old_mwh"] - per_sg["annual_new_mwh"]
    per_sg["delta_pct"] = (
        (per_sg["annual_old_mwh"] / per_sg["annual_new_mwh"] - 1) * 100
    ).where(per_sg["annual_new_mwh"] > 0)
    per_sg["rank_old"] = per_sg["annual_old_mwh"].rank(ascending=False, method="first")
    per_sg["rank_new"] = per_sg["annual_new_mwh"].rank(ascending=False, method="first")
    return per_sg


def main(results_dir_str: str) -> None:
    results_dir = Path(results_dir_str)
    edges = load_edges(results_dir)
    per_sg = aggregate_per_subgraph(edges)
    summary = load_summary(results_dir)

    print(f"=== Static A/B: demand aggregation (case dir: {results_dir.name}) ===\n")

    total_new = per_sg["annual_new_mwh"].sum()
    total_old = per_sg["annual_old_mwh"].sum()
    print(f"Subgraphs in lhd_graph:      {len(per_sg)}  (full_results summary: {summary.get('total_subgraphs')})")
    print(f"Total demand NEW (sum):      {total_new:,.1f} MWh/a  (summary: {summary.get('total_heat_demand_mwh'):,.1f})")
    print(f"Total demand OLD (mean*L):   {total_old:,.1f} MWh/a")
    print(f"Total delta:                 {total_old - total_new:+,.1f} MWh/a ({(total_old / total_new - 1) * 100:+.2f}%)")
    match = abs(total_new - summary.get("total_heat_demand_mwh", 0)) < 1.0
    print(f"Validation vs summary:       {'OK' if match else 'MISMATCH'}\n")

    d = per_sg["delta_pct"]
    print("Per-subgraph delta (old vs new annual demand):")
    print(f"  mean {d.mean():+.2f}%  median {d.median():+.2f}%  min {d.min():+.2f}%  max {d.max():+.2f}%")
    print(f"  share of subgraphs |delta| > {FLH_THRESHOLD_PCT}%: {(d.abs() > FLH_THRESHOLD_PCT).mean() * 100:.1f}%")
    print(f"  subgraphs with delta > 0 (old overstated): {(d > 0.01).sum()} / {len(per_sg)}")
    print(f"  subgraphs with delta < 0 (old understated): {(d < -0.01).sum()} / {len(per_sg)}\n")

    rank_corr = per_sg["annual_old_mwh"].corr(per_sg["annual_new_mwh"], method="spearman")
    max_rank_shift = (per_sg["rank_old"] - per_sg["rank_new"]).abs().max()
    seed_old = int(per_sg["annual_old_mwh"].idxmax())
    seed_new = int(per_sg["annual_new_mwh"].idxmax())
    print("Ranking / seed:")
    print(f"  Spearman rank corr (old vs new demand order): {rank_corr:.4f}")
    print(f"  max rank position shift: {max_rank_shift:.0f}")
    print(f"  seed under OLD: subgraph {seed_old} ({per_sg.loc[seed_old, 'annual_old_mwh']:,.0f} MWh/a)")
    print(f"  seed under NEW: subgraph {seed_new} ({per_sg.loc[seed_new, 'annual_new_mwh']:,.0f} MWh/a)")
    print(f"  seed identical: {seed_old == seed_new}\n")

    pearson = edges["length_m"].corr(edges["linear_heat_density"])
    spearman = edges["length_m"].corr(edges["linear_heat_density"], method="spearman")
    pooled_unweighted = edges["linear_heat_density"].mean()
    pooled_weighted = edges["heat_demand_mwh"].sum() / edges["length_m"].sum()
    print("Edge-level diagnostics (explanation of direction):")
    print(f"  corr(length, LHD): pearson {pearson:+.3f}, spearman {spearman:+.3f}")
    print(f"  pooled unweighted mean LHD: {pooled_unweighted:.3f} MWh/m/a")
    print(f"  pooled length-weighted mean LHD: {pooled_weighted:.3f} MWh/m/a")
    print(f"  -> old formula {'overstated' if pooled_unweighted > pooled_weighted else 'understated'} demand "
          f"by {(pooled_unweighted / pooled_weighted - 1) * 100:+.2f}% network-wide\n")

    top = per_sg.reindex(per_sg["delta_pct"].abs().sort_values(ascending=False).index).head(10)
    cols = ["edges", "buildings", "length_m", "annual_old_mwh", "annual_new_mwh", "delta_pct", "rank_old", "rank_new"]
    print("Top-10 subgraphs by |delta%|:")
    print(top[cols].to_string(float_format=lambda x: f"{x:,.2f}"))

    out_csv = results_dir / "aggregation_ab_static.csv"
    per_sg.to_csv(out_csv, float_format="%.6f")
    print(f"\nPer-subgraph table written to {out_csv}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "outputs/kamen_2026-08-26_13-22-13"
    main(target)
