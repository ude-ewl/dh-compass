import numpy as np
import pandas as pd


def source_temperature(temperature, source):
    if source == "air":
        source_temp = temperature.astype(float)
    elif source == "ground":
        source_temp = (temperature - 5).astype(float)
    elif source == "groundwater":
        source_temp = pd.Series(
            [10.0] * len(temperature), index=temperature.index, name="temperature"
        )
    elif source == "river":
        day_frac = np.arange(len(temperature)) / 24.0
        source_temp = pd.Series(
            12.1 + 6.7 * np.cos(2 * np.pi * (day_frac / 365 - 201 / 365)),
            index=temperature.index,
        )
    elif source == "wwtp":
        day_frac = np.arange(len(temperature)) / 24.0
        source_temp = pd.Series(
            15.0 + 4.0 * np.cos(2 * np.pi * (day_frac / 365 - 200 / 365)),
            index=temperature.index,
        )
    else:
        raise ValueError(f"Invalid source type: {source}")
    return source_temp


def sink_temperature(temperature, sink):
    if sink == "radiator":
        sink_temp = 40 - temperature
    elif sink == "floor":
        sink_temp = 30 - temperature * 0.5
    elif sink == "water":
        sink_temp = pd.Series(
            [50] * len(temperature), index=temperature.index, name="temperature"
        )
    elif sink == "dh_medium":
        sink_temp = (80 - temperature).clip(lower=65, upper=90)
    elif sink == "dh_low":
        sink_temp = (62 - 0.8 * temperature).clip(lower=50, upper=70)
    elif sink == "dh_high":
        sink_temp = (102 - 1.8 * temperature).clip(lower=75, upper=120)
    else:
        raise ValueError("Invalid sink type")
    return sink_temp


def cop_calc(source, sink, temperature, weights):
    temp_diff = source_temperature(temperature, source).astype(float) - (
        weights * sink_temperature(temperature, sink).astype(float)
        + (1 - weights) * sink_temperature(temperature, sink="water").astype(float)
    )
    delta_t = abs(temp_diff)

    # calculation of cop based on cop parameters (vectorized)
    delta_t_arr = delta_t.to_numpy(dtype=float)
    if source == "air":
        cop_arr = 6.08 - 0.09 * delta_t_arr + 0.0005 * delta_t_arr**2
    elif source == "ground":
        cop_arr = 10.29 - 0.21 * delta_t_arr + 0.0012 * delta_t_arr**2

    cop = (cop_arr * 0.85).tolist()

    return cop


def cop_carnot(source_temp, sink_temp, eta, max_cop=8.0):
    """Semi-empirical Carnot COP for large-scale heat pumps.

    COP = eta * T_sink_K / (T_sink_K - T_source_K)

    Parameters
    ----------
    source_temp : pd.Series
        Heat source temperature time series in degrees C.
    sink_temp : pd.Series
        Heat sink (delivery) temperature time series in degrees C.
    eta : float
        Second-law efficiency (quality grade), typically 0.45-0.55.
    max_cop : float
        Upper cap to prevent unrealistic values at small temperature differences.

    Returns
    -------
    list[float]
        Hourly COP time series.
    """
    t_sink_k = sink_temp.astype(float) + 273.15
    t_source_k = source_temp.astype(float) + 273.15
    dt = (t_sink_k - t_source_k).clip(lower=1)
    cop = eta * t_sink_k / dt
    cop = cop.clip(upper=max_cop)
    return cop.tolist()
