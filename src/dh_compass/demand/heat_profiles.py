from pathlib import Path

import numpy as np
import pandas as pd

from dh_compass.config import PathConfig
from dh_compass.demand.slp_inputs import WEEKDAYS, read_slp_tables

try:
    import holidays
except ImportError:  # pragma: no cover - optional until profile generation
    holidays = None

HOURS_IN_A_DAY = 24
REFERENCE_TEMPERATURE = 40

_slp_excel_cache = {}
_holiday_cache = {}


def _default_paths() -> PathConfig:
    return PathConfig.from_project_root()


def _load_slp_excel(slp_path: Path | None = None, profiles=()):
    data_path = Path(slp_path or _default_paths().slp_parameters)
    data_key = (str(data_path.resolve()), data_path.stat().st_mtime_ns if data_path.exists() else None, profiles)
    if data_key not in _slp_excel_cache:
        _slp_excel_cache[data_key] = read_slp_tables(data_path, profiles)
    return _slp_excel_cache[data_key]


def generate_slp_from_temperatures(
    year, category, characteristics, total_demand_heat, temperature_data,
    *, slp_path: Path | None = None
):
    """
    Generates a slp timeseries for a specific category with predefined characteristics.

    Parameters
    ----------
    year : int
        Year for which the temperature timeseries needs to be generated.
    selected_location : str
        Location identifier.
    category: str
        Specification of categories that shall be used for creation of the slp timeseries.
    characteristics: str
        Specification of characteristics for the different load profiles.
    total_demand_heat : float
        Total annual heat demand in kWh.

    Returns
    -------
    df_load : pd.DataFrame
        Heat SLP Profile for the specified category and characteristics.
    """
    temps = temperature_data.rename(columns={"Datum": "datetime"})
    utc_dates = pd.DatetimeIndex(pd.to_datetime(temps["datetime"], utc=True))
    local_dates = utc_dates.tz_convert("Europe/Berlin")

    holiday_key = (year, "NW")
    if holiday_key not in _holiday_cache:
        _holiday_cache[holiday_key] = holidays.Germany(
            years=[year - 1, year, year + 1], subdiv="NW"
        )
    de_holidays = _holiday_cache[holiday_key]

    df_parameters, df_daily_factors = _load_slp_excel(slp_path, ((category, characteristics),))

    parameter = None
    for index, row in df_parameters.iterrows():
        if row["category"] == category and row["characteristics"] == characteristics:
            parameter = row.to_dict()
            break

    daily_factors = None
    for index, row in df_daily_factors.iterrows():
        if row["category"] == category:
            daily_factors = [row[column] for column in WEEKDAYS]
            break

    if parameter is None or daily_factors is None:
        raise ValueError(f"SLP input has no profile for {category}/{characteristics}; see docs/slp-inputs.md")

    temperatures = temps["temperature"].values
    datetimes = local_dates

    h_sigmoid = (
        parameter["A"]
        / (
            1
            + np.power(
                parameter["B"] / (temperatures - REFERENCE_TEMPERATURE), parameter["C"]
            )
        )
        + parameter["D"]
    )
    h_linear = np.maximum(
        parameter["m_H"] * temperatures + parameter["b_H"],
        parameter["m_w"] * temperatures + parameter["b_w"],
    )
    h_values = h_sigmoid + h_linear

    weekdays = np.array([pd.Timestamp(d).weekday() for d in datetimes])
    is_holiday = np.array([pd.Timestamp(d).date() in de_holidays for d in datetimes])

    factor_array = np.ones(len(temps))
    for wd in range(7):
        mask = weekdays == wd
        factor_array[mask] = daily_factors[wd]
    factor_array[is_holiday] = daily_factors[6]
    factor_array[(weekdays == 6) & ~is_holiday] = daily_factors[6]

    h_values = h_values * factor_array

    scaling_factor = total_demand_heat / h_values.sum()
    load_values = h_values * scaling_factor

    df_load = pd.DataFrame({"datetime": temps["datetime"], "load": load_values})

    return df_load


def scaling_minmax_adv(profile, max_demand, total_demand):
    """

    Parameters
    ----------
    profile : initial timeseries
    max_demand : intended maximum value of timeseries
    total_demand : intended total sum over all timeseries elements

    Returns
    -------
    x : adjusted timeseries with maximum point x_max and total sum x_sum

    """
    if isinstance(profile, list):
        x0 = [0] * len(profile)
        for i in range(0, len(profile)):
            x0[i] = profile[i]
        x0 = np.asarray(x0)
    else:
        x0 = profile

    # Compute basic
    x0_min = np.min(x0)
    n_x = len(x0)
    x0_dminmax = np.max(x0) - x0_min
    x0_summax = np.sum(x0) - x0_min * n_x

    # Compute factors
    f = (total_demand - n_x * max_demand) / (x0_summax - x0_dminmax * n_x)
    x_min = max_demand - f * x0_dminmax

    # Compute
    scaled_profile = np.full(n_x, x_min) + (x0 - x0_min) * np.full(n_x, f)

    # check, if there are result values below zero (possible, if parameters are poorly chosen).
    # If yes, search for most negative value and add it to all values so that the minimum becomes zero.
    # Finally, rescale profile s.t. sum fits again; display that numbers don't align well with the profile.

    if np.min(scaled_profile) < 0:
        scaled_profile = scaled_profile - np.min(scaled_profile)
        x_sum_new = np.sum(scaled_profile)
        scaling = total_demand / x_sum_new
        scaled_profile = scaling * scaled_profile
        print(
            "Maximum load and total annual heat demand cannot be scaled to the selected profile. "
            "Maximum load was adjusted to ",
            np.round(np.max(scaled_profile)),
            "kW.",
        )

    return scaled_profile
