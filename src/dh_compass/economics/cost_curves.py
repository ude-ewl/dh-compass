from functools import partial
from pathlib import Path

import pandas as pd


# Functions
def read_ts_data(filepath):
    """Read calendar factors, retaining support for existing Excel overrides."""
    if Path(filepath).suffix.lower() == ".csv":
        ts_data = pd.read_csv(filepath, float_precision="round_trip")
        ts_data["Datum"] = pd.to_datetime(ts_data["Datum"], errors="raise", format="ISO8601")
    else:
        ts_data = pd.read_excel(filepath)
    return ts_data, len(ts_data["Datum"]), len(ts_data["Datum"]) / 24


def calculate_invest_cost(cost_structure):
    # Sort the cost structure by keys (range_start)
    sorted_ranges = sorted(cost_structure.keys())
    sorted_costs = [cost_structure[k] for k in sorted_ranges]

    def invest_cost_function(x):
        # Find the appropriate cost for the given investment size
        for i in range(len(sorted_ranges) - 1, -1, -1):
            if x >= sorted_ranges[i]:
                return sorted_costs[i]
        return sorted_costs[0]  # Return the smallest cost if x is smaller than the smallest range

    return invest_cost_function

def calculate_invest_cost_interpolated(capacity, *, cost_structure: dict[float, float]) -> float:
    """Interpoliert (linear) die Kosten für eine gegebene Kapazität."""
    thresholds = sorted(cost_structure)                 # sortierte Grenzwerte
    if capacity <= thresholds[0]:                       # links außen
        return cost_structure[thresholds[0]]
    if capacity >= thresholds[-1]:                      # rechts außen
        return cost_structure[thresholds[-1]]

    # benachbarte Schwellen suchen
    for idx in range(1, len(thresholds)):
        if capacity < thresholds[idx]:
            low, up = thresholds[idx - 1], thresholds[idx]
            break

    # lineares Intervall‑Interpolieren
    lc, uc = cost_structure[low], cost_structure[up]
    return lc + (uc - lc) * (capacity - low) / (up - low)

def make_cost_func(structure):
    """Erzeugt eine Ein‑Parameter‑Funktion mit fixierter Kostenstruktur."""
    return partial(calculate_invest_cost_interpolated, cost_structure=structure)

def calculate_reinvest_and_residual_value_factors(tech_list, interest_rate, investment_duration, annual_change):
    for tech in tech_list:
        if tech[0]["lifetime"] < investment_duration:
            tech[0]["reinvest_factor"] = reinvest_factor(interest_rate, tech[0]["lifetime"], annual_change)
        tech[0]["residual_value_factor"] = residual_value_factor(
            interest_rate,
            tech[0]["lifetime"],
            investment_duration,
            annual_change
        )


def reinvest_factor(interest_rate, tech_lifetime, invest_cost_annual_change):
    """
    Calculates a reinvest factor according to VDI 2067.

    Parameters
    ----------
    interest_rate : float
        Discount rate used in dynamic investment appraisal methods.
    tech_lifetime : int
        Lifetimes of technologies
    invest_cost_annual_change : int
        Percentage of annual change of investment costs

    Returns
    -------
    ri_f : float
        Reinvest factor according to VDI 2067.

    """
    ri_f = (invest_cost_annual_change ** tech_lifetime) / ((1 + interest_rate) ** tech_lifetime)

    return ri_f


def residual_value_factor(interest_rate, tech_lifetime, investment_duration, invest_cost_annual_change):
    """
    Calculates a residual value factor according to VDI 2067.

    Parameters
    ----------
    interest_rate : float
        Discount rate used in dynamic investment appraisal methods.
    tech_lifetime : int
        Lifetimes of technologies
    investment_duration : int
        Duration of the investment period in years.
    invest_cost_annual_change : float
        Percentage of annual change of investment costs

    Returns
    -------
    res_f : float
        Residual value factor according to VDI 2067.

    """
    res_f = (invest_cost_annual_change ** ((tech_lifetime < investment_duration) * tech_lifetime)
             * ((((tech_lifetime < investment_duration) + 1) * tech_lifetime - investment_duration)
                / tech_lifetime) * 1/((1 + interest_rate) ** investment_duration))

    return res_f
