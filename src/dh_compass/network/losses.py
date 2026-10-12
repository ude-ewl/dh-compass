"""Constant fractional DH distribution losses, separate from generator losses."""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite

import pandas as pd


def validate_heat_loss_fraction(value: float) -> None:
    """Reject invalid fractions before constructing a model or sizing a pump."""
    if isinstance(value, bool) or not isfinite(value) or not 0 <= value < 1:
        raise ValueError("network.heat_loss_fraction must be finite and in [0, 1)")


def network_input_heat(
    delivered_heat: Sequence[float] | pd.Series, loss_fraction: float
) -> Sequence[float] | pd.Series:
    """Convert delivered heat to network input without mutating the profile.

    Losses are a fraction of network input, not an uplift on delivered demand.
    Preserve Series indexes and the original object for loss-free runs.
    """
    validate_heat_loss_fraction(loss_fraction)
    if loss_fraction == 0:
        return delivered_heat
    if isinstance(delivered_heat, pd.Series):
        return delivered_heat / (1 - loss_fraction)
    return [value / (1 - loss_fraction) for value in delivered_heat]
