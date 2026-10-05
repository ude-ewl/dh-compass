"""Distribution and connection cost functions."""

from __future__ import annotations

from functools import partial
from typing import Callable, Mapping

from dh_compass.economics.cost_curves import make_cost_func, residual_value_factor


def _default_network_cost_tables() -> dict[str, Mapping]:
    """Load fallback cost tables from the canonical TOML configuration.

    The fallback keeps the small network helpers usable by notebooks and
    preprocessing callers that do not yet pass an :class:`AppConfig`.  It is
    deliberately lazy so importing this module never reads configuration files.
    """

    from dh_compass.config import load_default_config

    network = load_default_config().network
    return {
        "distribution": network.distribution_pipe_cost_coefficients,
        "connection": network.building_connection_cost_coefficients,
        "transfer_station": network.transfer_station_cost_structure,
        "pump": network.pump_cost_structure,
    }


def distribution_pipe_cost_func(
    power_kwth: float,
    coefficients: Mapping[str, float] | None = None,
) -> float:
    coefficients = coefficients or _default_network_cost_tables()["distribution"]
    return float(coefficients["a"] * power_kwth ** coefficients["b"])


def building_connection_cost_func(
    power_kwth: float,
    coefficients: Mapping[str, float] | None = None,
) -> float:
    coefficients = coefficients or _default_network_cost_tables()["connection"]
    return float(coefficients["a"] * power_kwth + coefficients["b"])


def transfer_station_cost_func(
    power_kwth: float,
    cost_structure: Mapping[float, float] | None = None,
) -> float:
    cost_structure = cost_structure or _default_network_cost_tables()["transfer_station"]
    return float(make_cost_func(cost_structure)(power_kwth) * (power_kwth / 1000.0))


def pump_cost_func(
    power_kwth: float,
    cost_structure: Mapping[float, float] | None = None,
) -> float:
    cost_structure = cost_structure or _default_network_cost_tables()["pump"]
    return float(make_cost_func(cost_structure)(power_kwth) * (power_kwth / 1000.0))


def build_network_cost_functions(
    *,
    distribution_coefficients: Mapping[str, float] | None = None,
    connection_coefficients: Mapping[str, float] | None = None,
    transfer_station_structure: Mapping[float, float] | None = None,
    pump_structure: Mapping[float, float] | None = None,
) -> dict[str, Callable[[float], float]]:
    """Build injectable network cost functions from explicit cost tables.

    If no tables are supplied, the values are loaded lazily from
    ``configs/default.toml``.  Production pipeline code passes the already
    loaded values from ``AppConfig`` so a run has one consistent configuration
    snapshot.
    """

    if any(
        value is None
        for value in (
            distribution_coefficients,
            connection_coefficients,
            transfer_station_structure,
            pump_structure,
        )
    ):
        defaults = _default_network_cost_tables()
        distribution_coefficients = (
            defaults["distribution"]
            if distribution_coefficients is None
            else distribution_coefficients
        )
        connection_coefficients = (
            defaults["connection"] if connection_coefficients is None else connection_coefficients
        )
        transfer_station_structure = (
            defaults["transfer_station"]
            if transfer_station_structure is None
            else transfer_station_structure
        )
        pump_structure = defaults["pump"] if pump_structure is None else pump_structure

    return {
        "distribution_pipe_cost_func": partial(
            distribution_pipe_cost_func, coefficients=distribution_coefficients
        ),
        "building_connection_cost_func": partial(
            building_connection_cost_func, coefficients=connection_coefficients
        ),
        "transfer_station_cost_func": partial(
            transfer_station_cost_func, cost_structure=transfer_station_structure
        ),
        "pump_cost_func": partial(pump_cost_func, cost_structure=pump_structure),
    }


__all__ = [
    "build_network_cost_functions",
    "building_connection_cost_func",
    "distribution_pipe_cost_func",
    "make_cost_func",
    "pump_cost_func",
    "residual_value_factor",
    "transfer_station_cost_func",
]
