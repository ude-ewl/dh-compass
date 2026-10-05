"""Factories for runtime demand, price, COP, and technology inputs.

This module intentionally contains no module-level data loading.  Expensive work
happens only when one of the factory functions is called with an explicit
configuration and path set.
"""

from __future__ import annotations

from copy import deepcopy

import pandas as pd

from dh_compass.config.models import (
    AppConfig,
    PathConfig,
    TechnologyInputs,
    TimeSeriesData,
)
from dh_compass.economics.cost_curves import (
    calculate_reinvest_and_residual_value_factors,
    make_cost_func,
    read_ts_data,
)


def load_time_series(paths: PathConfig, config: AppConfig) -> TimeSeriesData:
    """Combine local weather with reference demand factors on one UTC timeline.

    Reference factors are a calendar template, not weather observations.
    Their month/day/hour pattern is applied in local German time; February 29
    uses February 28 when the template has no leap day.
    """

    from dh_compass.demand.weather import load_weather

    path = paths.historical_timeseries
    if not path.exists():
        raise FileNotFoundError(
            f"Historical time-series input not found: {path}. "
            "Restore the project ratio CSV; see data/README.md or override paths.historical_timeseries."
        )
    reference, _, _ = read_ts_data(path)
    if "Datum" not in reference:
        raise ValueError(
            f"Reference demand factors {path} must contain a Datum column"
        )
    weather = load_weather(config)
    data = weather.data.rename(columns={"datetime": "Datum"}).copy()
    if "sh_to_wh_ratio" in reference:
        reference_dates = pd.to_datetime(reference["Datum"], errors="raise")
        # Excel serial dates in the bundled hourly template can be a few
        # milliseconds before the intended hour. Correct serialization noise,
        # but do not silently round genuinely sub-hourly observations.
        rounded_dates = reference_dates.dt.round("h")
        if ((reference_dates - rounded_dates).abs() > pd.Timedelta(seconds=1)).any():
            raise ValueError("Reference demand factors must have hourly timestamps.")
        reference_dates = rounded_dates
        calendar = pd.MultiIndex.from_arrays(
            [reference_dates.dt.month, reference_dates.dt.day, reference_dates.dt.hour]
        )
        ratios = pd.Series(
            pd.to_numeric(reference["sh_to_wh_ratio"], errors="raise").to_numpy(),
            index=calendar,
        ).groupby(level=[0, 1, 2]).mean()
        local_dates = data["Datum"].dt.tz_convert("Europe/Berlin")
        keys = pd.MultiIndex.from_arrays(
            [local_dates.dt.month, local_dates.dt.day, local_dates.dt.hour]
        )
        factors = pd.Series(ratios.reindex(keys).to_numpy(), index=data.index, dtype=float)
        leap_missing = factors.isna() & (local_dates.dt.month == 2) & (local_dates.dt.day == 29)
        if leap_missing.any():
            fallback_keys = pd.MultiIndex.from_arrays(
                [[2] * int(leap_missing.sum()), [28] * int(leap_missing.sum()),
                 local_dates.loc[leap_missing].dt.hour]
            )
            factors.loc[leap_missing] = ratios.reindex(fallback_keys).to_numpy()
        if factors.isna().any() or not factors.between(0, 1).all():
            raise ValueError("Reference sh_to_wh_ratio must cover all calendar hours with values in [0, 1].")
        data["sh_to_wh_ratio"] = factors
    data.attrs["weather"] = weather.provenance
    length = len(data)
    return TimeSeriesData(
        data=data,
        timestamps=data["Datum"],
        length=length,
        days=length / 24,
    )


def _constant_series(value: float, length: int) -> list[float]:
    return [float(value)] * length


def _load_variable_electricity_prices(
    paths: PathConfig, timestamps: pd.Series | None = None
) -> list[float]:
    """Load and normalize the optional market-price data set."""

    epex_path = paths.reference_data / "EPEX SPOT DE-LU (Phelix) Stunden.xlsx"
    phelix_2022_path = paths.reference_data / "EEX Phelix-DE Baseload Cal-2022.xlsx"
    phelix_2024_path = paths.reference_data / "EEX Phelix-DE Baseload Cal-2024.xlsx"
    for path in (epex_path, phelix_2022_path, phelix_2024_path):
        if not path.exists():
            raise FileNotFoundError(f"Variable electricity-price input not found: {path}. Obtain an authorized copy; see data/README.md.")

    epex_data = pd.read_excel(epex_path, skiprows=4)
    epex_data["Datetime"] = pd.to_datetime(
        epex_data["Datum"], format="%d.%m.%Y"
    ) + pd.to_timedelta(epex_data["Stunde"] - 1, unit="h")
    epex_data = epex_data.set_index("Datetime")
    epex_data = epex_data.drop(columns=["Datum", "Stunde", "Umsatz"])

    phelix_2022_data = pd.read_excel(phelix_2022_path, skiprows=4, index_col=0)
    phelix_2022_data.index = phelix_2022_data.index.date
    phelix_2024_data = pd.read_excel(phelix_2024_path, skiprows=4, index_col=0)

    daily_data = pd.DataFrame(
        index=pd.to_datetime(sorted(set(epex_data.index.date))), columns=["Preis"]
    )
    daily_data.index = daily_data.index.date
    daily_data["Preis"] = daily_data["Preis"].fillna(phelix_2022_data["Preis"])
    first_non_nan = daily_data["Preis"].dropna().iloc[0]
    daily_data["Preis"] = daily_data["Preis"].fillna(first_non_nan, limit=3)
    daily_data["Preis"] = daily_data["Preis"].interpolate(
        method="linear", limit_direction="forward"
    )
    rolling_avg = daily_data["Preis"].rolling(window=7, min_periods=1).mean()
    epex_data["Date"] = epex_data.index.date
    epex_data["Normalisierter Preis"] = epex_data["Preis"] / epex_data["Date"].map(
        rolling_avg
    )
    epex_data["Preis 2024"] = (
        epex_data["Normalisierter Preis"] * phelix_2024_data["Preis"].mean()
    )
    prices = epex_data["Preis 2024"] / 1000
    if timestamps is not None:
        # This bundled market dataset is a calendar template, not observations
        # for the selected weather location. Match local hours explicitly.
        calendar = pd.MultiIndex.from_arrays(
            [prices.index.month, prices.index.day, prices.index.hour]
        )
        template = pd.Series(prices.to_numpy(), index=calendar).groupby(level=[0, 1, 2]).mean()
        local = pd.DatetimeIndex(timestamps).tz_convert("Europe/Berlin")
        prices = template.reindex(
            pd.MultiIndex.from_arrays([local.month, local.day, local.hour])
        )
        if prices.isna().any():
            raise ValueError("Variable electricity-price template does not cover all local calendar hours.")
    return [float(value) for value in prices]


def build_technology_inputs(
    paths: PathConfig,
    config: AppConfig,
    time_series: TimeSeriesData,
) -> TechnologyInputs:
    """Construct all arrays and cost functions required by the optimizer."""

    economics = config.economics
    demand = config.demand
    tech = config.technologies
    length = time_series.length
    data = time_series.data

    fuel_price_central = _constant_series(economics.fuel_price_central, length)
    fuel_price_decentral = _constant_series(economics.fuel_price_decentral, length)
    if demand.prices_fixed:
        elec_price_central = _constant_series(economics.electricity_price_central, length)
        elec_price_decentral = _constant_series(economics.electricity_price_decentral, length)
    else:
        if config.demand.slp_year != 2022:
            raise ValueError(
                "The bundled variable electricity-price template covers 2022 only. "
                "Use fixed prices for other weather years."
            )
        elec_price_central = elec_price_decentral = _load_variable_electricity_prices(
            paths, time_series.timestamps
        )

    price_sell_pv = _constant_series(economics.price_sell_pv, length)
    price_sell_chp = _constant_series(economics.price_sell_chp, length)
    fuel_price_biomass = _constant_series(economics.fuel_price_biomass, length)

    # Work on copies: calculating replacement/residual factors must not mutate
    # the immutable configuration object or affect another run in the process.
    battery_storage = deepcopy(tech.battery_storage)
    chp = deepcopy(tech.chp)
    boiler_decentral = deepcopy(tech.boiler_decentral)
    boiler_central = deepcopy(tech.boiler_central)
    heat_pump_decentral = deepcopy(tech.heat_pump_decentral)
    heat_pump_central = deepcopy(tech.heat_pump_central)
    heat_storage_decentral = deepcopy(tech.heat_storage_decentral)
    heat_storage_central = deepcopy(tech.heat_storage_central)
    electrode_boiler = deepcopy(tech.electrode_boiler)
    industrial_eh = deepcopy(tech.industrial_eh)
    biomass_boiler = deepcopy(tech.biomass_boiler)
    biomass_chp = deepcopy(tech.biomass_chp)
    waste_to_energy = deepcopy(tech.waste_to_energy)
    geothermal = deepcopy(tech.geothermal)
    river_heat_pump = deepcopy(tech.river_heat_pump)
    wwtp_heat_pump = deepcopy(tech.wwtp_heat_pump)

    calculate_reinvest_and_residual_value_factors(
        [
            battery_storage,
            chp,
            boiler_central,
            boiler_decentral,
            heat_pump_central,
            heat_pump_decentral,
            heat_storage_central,
            heat_storage_decentral,
            electrode_boiler,
            industrial_eh,
            biomass_boiler,
            biomass_chp,
            waste_to_energy,
            geothermal,
            river_heat_pump,
            wwtp_heat_pump,
        ],
        economics.interest_rate,
        economics.investment_duration,
        economics.invest_cost_annual_change,
    )

    from dh_compass.demand.cop import (
        cop_calc,
        cop_carnot,
        sink_temperature,
        source_temperature,
    )

    temperature = data["temperature"]
    weights = data.get("sh_to_wh_ratio", pd.Series(0.0, index=data.index))
    cop = cop_calc(demand.source, demand.sink, temperature, weights)
    supply_central = sink_temperature(temperature, demand.sink_central).astype(float)
    return_central = (supply_central - demand.dh_spread).clip(lower=1)
    sink_mean = (supply_central + return_central) / 2
    cop_central = cop_carnot(
        source_temperature(temperature, demand.source_central),
        sink_mean,
        demand.carnot_eta,
    )
    cop_central_river = cop_carnot(
        source_temperature(temperature, "river"), sink_mean, demand.carnot_eta
    )
    cop_central_wwtp = cop_carnot(
        source_temperature(temperature, "wwtp"), sink_mean, demand.carnot_eta
    )

    cost = economics.cost_structures
    fixed = economics.fixed_cost_structures
    variable = economics.variable_om_cost_structures
    inv_cost = {
        "chp": make_cost_func(cost["chp"]),
        "hb": {
            "decentral": make_cost_func(cost["hb_decentral"]),
            "central": make_cost_func(cost["hb_central"]),
        },
        "hs": {
            "decentral": make_cost_func(cost["hs_decentral"]),
            "central": make_cost_func(cost["hs_central"]),
        },
        "bs": make_cost_func(cost["bs"]),
        "hp": {
            "decentral": make_cost_func(cost["hp_decentral"]),
            "central": make_cost_func(cost["hp_central"]),
        },
        "eb": make_cost_func(cost["eb"]),
        "ieh": make_cost_func(cost["ieh"]),
        "bm_hb": make_cost_func(cost["bm_hb"]),
        "bm_chp": make_cost_func(cost["bm_chp"]),
        "wte": make_cost_func(cost["wte"]),
        "geo": make_cost_func(cost["geo"]),
        "hp_river": make_cost_func(cost["hp_river"]),
        "hp_wwtp": make_cost_func(cost["hp_wwtp"]),
    }
    fixed_cost = {
        "chp": make_cost_func(fixed["chp"]),
        "hb": {
            "decentral": make_cost_func(fixed["hb_decentral"]),
            "central": make_cost_func(fixed["hb_central"]),
        },
        "hs": make_cost_func(fixed["hs"]),
        "bs": make_cost_func(fixed["bs"]),
        "hp": {
            "decentral": make_cost_func(fixed["hp_decentral"]),
            "central": make_cost_func(fixed["hp_central"]),
        },
        "eb": make_cost_func(fixed["eb"]),
        "ieh": make_cost_func(fixed["ieh"]),
        "bm_hb": make_cost_func(fixed["bm_hb"]),
        "bm_chp": make_cost_func(fixed["bm_chp"]),
        "wte": make_cost_func(fixed["wte"]),
        "geo": make_cost_func(fixed["geo"]),
        "hp_river": make_cost_func(fixed["hp_river"]),
        "hp_wwtp": make_cost_func(fixed["hp_wwtp"]),
    }
    var_om_cost = {
        "chp": make_cost_func(variable["chp"]),
        "hb": {"central": make_cost_func(variable["hb_central"])},
        "ieh": make_cost_func(variable["ieh"]),
        "bm_hb": make_cost_func(variable["bm_hb"]),
        "bm_chp": make_cost_func(variable["bm_chp"]),
        "wte": make_cost_func(variable["wte"]),
        "geo": make_cost_func(variable["geo"]),
        "hp_river": make_cost_func(variable["hp_river"]),
        "hp_wwtp": make_cost_func(variable["hp_wwtp"]),
    }

    return TechnologyInputs(
        timestamps=time_series.timestamps,
        fuel_price_central=fuel_price_central,
        fuel_price_decentral=fuel_price_decentral,
        elec_price_central=elec_price_central,
        elec_price_decentral=elec_price_decentral,
        price_sell_pv=price_sell_pv,
        price_sell_chp=price_sell_chp,
        fuel_price_biomass=fuel_price_biomass,
        electricity_price_annual_change=economics.electricity_price_annual_change,
        gas_price_annual_change=economics.gas_price_annual_change,
        pv_rem_annual_change=economics.pv_rem_annual_change,
        chp_rem_annual_change=economics.chp_rem_annual_change,
        pv_infeed=[0.0] * length,
        cop=cop,
        cop_central=cop_central,
        cop_central_river=cop_central_river,
        cop_central_wwtp=cop_central_wwtp,
        solar_heat=[0.0] * length,
        battery_storage=battery_storage,
        chp=chp,
        chp_decentral=deepcopy(tech.no_chp),
        boiler_central=boiler_central,
        boiler_decentral=boiler_decentral,
        heat_pump_central=heat_pump_central,
        heat_pump_decentral=heat_pump_decentral,
        electrode_boiler=electrode_boiler,
        heat_storage_central=heat_storage_central,
        heat_storage_decentral=heat_storage_decentral,
        industrial_eh=industrial_eh,
        no_industrial_eh=deepcopy(tech.no_industrial_eh),
        biomass_boiler=biomass_boiler,
        no_biomass_boiler=deepcopy(tech.no_biomass_boiler),
        biomass_chp=biomass_chp,
        no_biomass_chp=deepcopy(tech.no_biomass_chp),
        waste_to_energy=waste_to_energy,
        no_waste_to_energy=deepcopy(tech.no_waste_to_energy),
        geothermal=geothermal,
        no_geothermal=deepcopy(tech.no_geothermal),
        river_heat_pump=river_heat_pump,
        no_river_heat_pump=deepcopy(tech.no_river_heat_pump),
        wwtp_heat_pump=wwtp_heat_pump,
        no_wwtp_heat_pump=deepcopy(tech.no_wwtp_heat_pump),
        inv_cost=inv_cost,
        fixed_cost=fixed_cost,
        var_om_cost=var_om_cost,
    )


def build_subgraph_profile_generator(
    paths: PathConfig, config: AppConfig, *, temperature_data: pd.DataFrame | None = None
):
    """Return the load-profile generator used for candidate areas."""

    unit_profile = None

    def generate(annual_demand_mwh: float):
        nonlocal temperature_data, unit_profile
        from dh_compass.demand.heat_profiles import generate_slp_from_temperatures
        from dh_compass.demand.weather import load_weather
        if temperature_data is None:
            temperature_data = load_weather(config).data

        if unit_profile is None:
            unit_profile = generate_slp_from_temperatures(
                config.demand.slp_year,
                config.demand.slp_profile_type_subgraph,
                config.demand.slp_temperature_zone,
                1000,
                temperature_data,
                slp_path=paths.slp_parameters,
            )
        return unit_profile.assign(load=unit_profile["load"] * annual_demand_mwh)

    return generate


def build_building_profile_generator(
    paths: PathConfig, config: AppConfig, *, temperature_data: pd.DataFrame | None = None
):
    """Return a lazy SLP generator bound to explicit input paths."""

    unit_profile = None

    def generate(annual_demand_mwh: float):
        nonlocal temperature_data, unit_profile
        from dh_compass.demand.heat_profiles import generate_slp_from_temperatures
        from dh_compass.demand.weather import load_weather
        if temperature_data is None:
            temperature_data = load_weather(config).data

        if unit_profile is None:
            unit_profile = generate_slp_from_temperatures(
                config.demand.slp_year,
                config.demand.slp_profile_type_building,
                config.demand.slp_temperature_zone,
                1000,
                temperature_data,
                slp_path=paths.slp_parameters,
            )["load"]
        return unit_profile * annual_demand_mwh

    return generate


__all__ = [
    "build_building_profile_generator",
    "build_subgraph_profile_generator",
    "build_technology_inputs",
    "load_time_series",
]
