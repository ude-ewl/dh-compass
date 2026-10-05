"""Industrial excess-heat availability calculations."""

from __future__ import annotations


def assess_industrial_heat(frame, bbox, scenario: str):
    selected = frame[frame.geometry.within(bbox)]
    energy_mwh = float(selected[scenario].sum()) * 1000 if len(selected) else 0.0
    return bool(len(selected)), energy_mwh


__all__ = ["assess_industrial_heat"]
