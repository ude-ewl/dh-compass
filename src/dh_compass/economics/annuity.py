# -*- coding: utf-8 -*-
"""
Python-Funktionen zur Berechnung betriebswirtschaftlicher Kennzahlen, aufgrund gegebener Optimierungsergebnisse und Kennzahlen.

Stand: 21.01.2021
Author: CF
"""
#import numpy as np
import math

import numpy_financial as npf


def annuity_factor(interest_rate: float, investment_duration: int) -> float:
    """Return the annualization factor for an investment period."""

    effective_rate = 1 + interest_rate
    return (effective_rate - 1) / (1 - effective_rate ** (-investment_duration))


def npv_factor(
    interest_rate: float, investment_duration: int, annual_change: float
) -> float:
    """Return the present-value factor for an annually changing cash flow."""

    effective_rate = 1 + interest_rate
    rate_diff = effective_rate - annual_change

    if rate_diff == 0:
        return investment_duration / effective_rate

    adjusted_annual_change = annual_change / effective_rate
    return (1 - adjusted_annual_change**investment_duration) / rate_diff


def net_present_value_adj(cashflow_year, initial_invest, interest_rate, reinvest_rate):
    """
    

    Parameters
    ----------
    cashflow_year : Array of cashflows over the lifetime of a plant, each value in [€/year]
    initial_invest : Initial investment in t=0 in €.
    discount_rate : interest rate ("Zinssatz") of investment in absolute numbers [-]
    reinvest_rate : payment needed for yearly reinvestment (for example in broken PV panels) as fraction of initial invest [-]

    Returns
    -------
    net_present_value : net present value ("Kapitalwert") in €

    """
    lifetime = len(cashflow_year)
    reinvest = [0]*len(cashflow_year)
    for i in range(1, lifetime):
        reinvest[i] = reinvest_rate * initial_invest
    net_present_value = -initial_invest - npf.npv(interest_rate, reinvest) + npf.npv(interest_rate, cashflow_year)
    return net_present_value

def amortisation_time(cashflow_year, initial_invest, reinvest_rate, interest_rate):
    """
    

    Parameters
    ----------
    cashflow_year : Array of cashflows over the lifetime of a plant, each value in [€/year]
    initial_invest : Initial investment in t=0 in €.
    reinvest_rate : payment needed for yearly reinvestment (for example in the replacement of broken PV panels) as fraction of initial invest [-]

    Returns
    -------
    amortisation_time : Years, until investment has been repaid (amortised) by the plant.

    """    
    lifetime = len(cashflow_year)
    reinvest = [0]*len(cashflow_year)

    for i in range(1, lifetime):
        reinvest[i] = reinvest_rate * initial_invest
    net_gainings = -initial_invest
    i = 0

    while net_gainings < 0 and i < lifetime:
        net_gainings = net_gainings + ((cashflow_year[i] - reinvest[i]) / ((1 + interest_rate)**i))
        i = i+1
    if net_gainings < 0:
        print('Project will not amortise during the plant s lifetime')
        amortisation_time = math.inf
    else: 
        amortisation_time = i
    
    return amortisation_time


def present_value_annuity(annuity, interest_rate, investment_duration):
    pv_annuity = (annuity / (1 + interest_rate)) * (1 - (1 / (1 + interest_rate) ** investment_duration))

    return pv_annuity
