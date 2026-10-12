"""Explicit delivered/network-input heat metrics for central result profiles."""

from __future__ import annotations

import pandas as pd

from ..network.losses import network_input_heat


def heat_balance_metrics(
    result_df: pd.DataFrame, dt: float, loss_fraction: float
) -> dict[str, float]:
    """Integrate losses, not production (which also includes storage/dumping).

    Older value-only frames have no network-input column; derive it from the
    delivered profile and the run's assumption, without changing either.
    """
    delivered = result_df["demand_heat"]
    network_input = (
        result_df["network_input_heat"]
        if "network_input_heat" in result_df
        else network_input_heat(delivered, loss_fraction)
    )
    return {
        "heat_loss_fraction": loss_fraction,
        "annual_network_input_heat_mwh": round(float(network_input.sum() * dt / 1000), 4),
        "annual_distribution_heat_loss_mwh": round(
            float((network_input - delivered).sum() * dt / 1000), 4
        ),
        "network_input_peak_load_kw": round(float(network_input.max()), 4),
    }
