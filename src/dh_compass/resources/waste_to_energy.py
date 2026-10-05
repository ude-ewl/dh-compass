"""Waste-to-energy potential calculations."""


def assess_waste_to_energy(frame, bbox, scenario: str):
    selected = frame[frame.geometry.within(bbox)]
    energy_mwh = float(selected[scenario].sum()) * 277.778 * 1000 if len(selected) else 0.0
    return energy_mwh > 0, energy_mwh


__all__ = ["assess_waste_to_energy"]
