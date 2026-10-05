from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import Patch

TECH_LABELS = {
    "heat_pump": "Heat Pump",
    "boiler": "Gas Boiler",
    "chp": "CHP",
    "electrode_boiler": "Electrode Boiler",
    "industrial_excess_heat": "Industrial Excess Heat",
    "biomass_boiler": "Biomass Boiler",
    "biomass_chp": "Biomass CHP",
    "waste_to_energy": "Waste-to-Energy",
    "geothermal": "Hydrothermal Geothermal",
    "river_heat_pump": "River HP",
    "wwtp_heat_pump": "WWTP HP",
}

TECH_COLORS = {
    "heat_pump": "#2196F3",
    "boiler": "#FF9800",
    "chp": "#4CAF50",
    "electrode_boiler": "#9C27B0",
    "industrial_excess_heat": "#795548",
    "biomass_boiler": "#8BC34A",
    "biomass_chp": "#33691E",
    "waste_to_energy": "#FF5722",
    "geothermal": "#E91E63",
    "river_heat_pump": "#00BCD4",
    "wwtp_heat_pump": "#009688",
}

GRID_COLORS = {
    "distribution_pipes": "#607D8B",
    "building_connections": "#795548",
    "transfer_stations": "#FFC107",
    "pumps": "#00BCD4",
    "connection_pipelines": "#E91E63",
}

GRID_LABELS = {
    "distribution_pipes": "Distribution Pipes",
    "building_connections": "Building Connections",
    "transfer_stations": "Transfer Stations",
    "pumps": "Pumps",
    "connection_pipelines": "Connection Pipelines",
}

SUPPLY_COST_COLORS = {
    "investment": "#1976D2",
    "fixed_om": "#64B5F6",
    "operational": "#BBDEFB",
}

COST_CATEGORY_COLORS = {
    "supply": "#2196F3",
    "grid": "#78909C",
}


_CHART_TECH_ORDER = (
    "heat_pump",
    "boiler",
    "chp",
    "electrode_boiler",
    "industrial_excess_heat",
    "biomass_boiler",
    "biomass_chp",
    "waste_to_energy",
    "geothermal",
    "river_heat_pump",
    "wwtp_heat_pump",
)


def plot_capacity_bar(supply: dict, out_path: str, title: str = "Installed Capacity"):
    techs, caps, colors = [], [], []
    for key in _CHART_TECH_ORDER:
        if key in supply:
            cap_key = "capacity_th_kw" if key in ("chp", "biomass_chp") else "capacity_kw"
            val = supply[key].get(cap_key, 0)
            if val > 0:
                techs.append(TECH_LABELS[key])
                caps.append(val)
                colors.append(TECH_COLORS[key])

    if not techs:
        return

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(techs, caps, color=colors, edgecolor="white", linewidth=0.8)
    ax.set_ylabel("Capacity [kW]")
    ax.set_title(title)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    for bar, val in zip(bars, caps):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{val:,.0f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_energy_pie(supply: dict, out_path: str, title: str = "Output Heat Energy"):
    labels, sizes, colors = [], [], []
    for key in _CHART_TECH_ORDER:
        if key in supply:
            e_key = (
                "annual_heat_energy_mwh"
                if key in ("chp", "biomass_chp")
                else "annual_energy_mwh"
            )
            val = supply[key].get(e_key, 0)
            share = supply[key].get("energy_share_pct", 0)
            if val > 0:
                labels.append(f"{TECH_LABELS[key]}\n{val:,.1f} MWh ({share:.1f}%)")
                sizes.append(val)
                colors.append(TECH_COLORS[key])

    if not sizes:
        return

    fig, ax = plt.subplots(figsize=(6, 6))
    wedges, texts = ax.pie(
        sizes,
        labels=labels,
        colors=colors,
        startangle=90,
        textprops={"fontsize": 9},
    )
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_cost_stacked(
    supply_breakdown: dict,
    grid_breakdown: dict,
    out_path: str,
    title: str = "Cost Structure",
):
    sup_inv = supply_breakdown.get("investment", {}).get("total_eur", 0)
    sup_fix = supply_breakdown.get("fixed_om", {}).get("total_eur", 0)
    sup_op = supply_breakdown.get("operational", {}).get(
        "net_operational_annual_eur", 0
    )
    grid_total = grid_breakdown.get("total_annualized_eur", 0)

    categories = ["Supply", "Grid Infrastructure"]
    inv_vals = [sup_inv, 0]
    fix_vals = [sup_fix, 0]
    op_vals = [sup_op, 0]
    grid_vals = [0, grid_total]

    fig, ax = plt.subplots(figsize=(6, 4))
    bottom = [0, 0]

    ax.bar(
        categories,
        inv_vals,
        bottom=bottom,
        label="Investment (ann.)",
        color=SUPPLY_COST_COLORS["investment"],
    )
    bottom = [b + v for b, v in zip(bottom, inv_vals)]
    ax.bar(
        categories,
        fix_vals,
        bottom=bottom,
        label="Fixed O&M",
        color=SUPPLY_COST_COLORS["fixed_om"],
    )
    bottom = [b + v for b, v in zip(bottom, fix_vals)]
    ax.bar(
        categories,
        op_vals,
        bottom=bottom,
        label="Operational",
        color=SUPPLY_COST_COLORS["operational"],
    )
    bottom = [b + v for b, v in zip(bottom, op_vals)]
    ax.bar(
        categories,
        grid_vals,
        bottom=bottom,
        label="Grid Infrastructure",
        color=COST_CATEGORY_COLORS["grid"],
    )
    bottom = [b + v for b, v in zip(bottom, grid_vals)]

    for i, total in enumerate(bottom):
        ax.text(
            i,
            total,
            f"{total:,.0f}",
            ha="center",
            va="bottom",
            fontsize=9,
            #fontweight="bold",
        )

    ax.set_ylabel("Annualized Cost [EUR/a]")
    ax.set_title(title, pad=20)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_ylim(0, max(bottom) * 1.15)
    ax.legend(loc="upper right", fontsize=10)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_cost_detailed(
    supply_breakdown: dict,
    grid_breakdown: dict,
    out_path: str,
    title: str = "Grid Infrastructure Cost Breakdown",
):
    raw_total = grid_breakdown.get("raw_total_eur", 0)
    ann_total = grid_breakdown.get("total_annualized_eur", 0)
    ann_ratio = ann_total / raw_total if raw_total > 0 else 1.0

    grid_items = {
        "Distribution Pipes": grid_breakdown.get("distribution_pipes_eur", 0) * ann_ratio,
        "Building Connections": grid_breakdown.get("building_connections_eur", 0) * ann_ratio,
        "Transfer Stations": grid_breakdown.get("transfer_stations_eur", 0) * ann_ratio,
        "Pumps": grid_breakdown.get("pumps_eur", 0) * ann_ratio,
        "Connection Pipes": grid_breakdown.get("connection_pipelines_eur", 0) * ann_ratio,
    }
    labels = list(grid_items.keys())
    vals = list(grid_items.values())
    colors = [
        GRID_COLORS[k]
        for k in (
            "distribution_pipes",
            "building_connections",
            "transfer_stations",
            "pumps",
            "connection_pipelines",
        )
    ]

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.barh(labels, vals, color=colors, edgecolor="white", linewidth=0.5)

    for bar, val in zip(bars, vals):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f" {val:,.0f}",
            va="center",
            fontsize=8,
        )

    ax.set_xlabel("Annualized Cost [EUR/a]")
    ax.set_title(title)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_xlim(0, max(vals) * 1.1)
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def plot_cost_pie(
    supply_breakdown: dict,
    grid_breakdown: dict,
    out_path: str,
    title: str = "Total Cost Breakdown",
):
    sup_inv = supply_breakdown.get("investment", {}).get("total_eur", 0)
    sup_fix = supply_breakdown.get("fixed_om", {}).get("total_eur", 0)
    sup_op = supply_breakdown.get("operational", {}).get(
        "net_operational_annual_eur", 0
    )

    raw_total = grid_breakdown.get("raw_total_eur", 0)
    ann_total = grid_breakdown.get("total_annualized_eur", 0)
    ann_ratio = ann_total / raw_total if raw_total > 0 else 1.0

    grid_dist = grid_breakdown.get("distribution_pipes_eur", 0) * ann_ratio
    grid_bldg = grid_breakdown.get("building_connections_eur", 0) * ann_ratio
    grid_xfer = grid_breakdown.get("transfer_stations_eur", 0) * ann_ratio
    grid_pump = grid_breakdown.get("pumps_eur", 0) * ann_ratio
    grid_conn = grid_breakdown.get("connection_pipelines_eur", 0) * ann_ratio

    slices = {
        "Supply Investment": (sup_inv, SUPPLY_COST_COLORS["investment"]),
        "Supply Fixed O&M": (sup_fix, SUPPLY_COST_COLORS["fixed_om"]),
        "Supply Operational": (sup_op, SUPPLY_COST_COLORS["operational"]),
        "Distribution Pipes": (grid_dist, GRID_COLORS["distribution_pipes"]),
        "Building Connections": (grid_bldg, GRID_COLORS["building_connections"]),
        "Transfer Stations": (grid_xfer, GRID_COLORS["transfer_stations"]),
        "Pumps": (grid_pump, GRID_COLORS["pumps"]),
        "Connection Pipelines": (grid_conn, GRID_COLORS["connection_pipelines"]),
    }

    labels, sizes, colors = [], [], []
    for lbl, (val, clr) in slices.items():
        if val > 0:
            total = sum(v for v, _ in slices.values())
            pct = val / total * 100 if total > 0 else 0
            labels.append(f"{lbl}\n{pct:.1f}%")
            sizes.append(val)
            colors.append(clr)

    if not sizes:
        return

    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, texts = ax.pie(
        sizes,
        labels=labels,
        colors=colors,
        startangle=90,
        textprops={"fontsize": 8},
        wedgeprops={"edgecolor": "white", "linewidth": 1},
    )

    legend_elements = [
        Patch(
            facecolor=COST_CATEGORY_COLORS["supply"], edgecolor="white", label="Supply"
        ),
        Patch(
            facecolor=COST_CATEGORY_COLORS["grid"],
            edgecolor="white",
            label="Grid Infrastructure",
        ),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=9)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def generate_all_charts(full_results: dict, output_dir: str | Path):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cg = full_results.get("combined_graph")
    if not cg:
        print("No combined_graph in results — skipping charts.")
        return

    supply = cg.get("supply", {})
    cost = cg.get("cost", {})
    supply_breakdown = cost.get("supply_breakdown", {})
    grid_breakdown = cost.get("grid_breakdown", {})

    plot_capacity_bar(supply, output_dir / "chart_capacity.png")
    plot_energy_pie(supply, output_dir / "chart_energy_shares.png")
    plot_cost_stacked(
        supply_breakdown,
        grid_breakdown,
        output_dir / "chart_cost_structure.png",
    )
    plot_cost_detailed(
        supply_breakdown,
        grid_breakdown,
        output_dir / "chart_cost_detailed.png",
    )
    plot_cost_pie(
        supply_breakdown,
        grid_breakdown,
        output_dir / "chart_cost_pie.png",
    )
    print(f"Charts saved to {output_dir}/")
