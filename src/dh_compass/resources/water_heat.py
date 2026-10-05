"""River/lake and wastewater heat-pump capacity calculations."""


def assess_river_heat(frame, bbox):
    selected = frame[frame.geometry.intersects(bbox)]
    capacity_kw = float(selected["Capa in MW"].sum()) * 1000 if len(selected) else 0.0
    return bool(len(selected)), capacity_kw


def assess_wwtp_heat(frame, bbox):
    selected = frame[frame.geometry.within(bbox)]
    capacity_kw = float(selected["Power in k"].sum()) if len(selected) else 0.0
    return bool(len(selected)), capacity_kw


__all__ = ["assess_river_heat", "assess_wwtp_heat"]
