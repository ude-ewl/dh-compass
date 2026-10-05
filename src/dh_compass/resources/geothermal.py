"""Hydrothermal/geothermal potential calculations."""


def assess_geothermal(frame, bbox, scenario: str):
    selected = frame[frame.geometry.intersects(bbox)]
    energy_mwh = float(selected[scenario].sum()) * 1_000_000 if len(selected) else 0.0
    return energy_mwh > 0, energy_mwh


__all__ = ["assess_geothermal"]
