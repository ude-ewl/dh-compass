"""Public composition entry point for the mathematical optimization model."""

from __future__ import annotations

import logging
from dataclasses import dataclass, fields, replace
from threading import Lock

from mip import GRB, HIGHS, Constr, InterfacingError, Model

from ..economics.annuity import annuity_factor, npv_factor
from .constraints import add_constraints
from .model_inputs import ModelInputs
from .objective import add_objective
from .variables import ModelVariables, create_variables

LOGGER = logging.getLogger(__name__)
_solver_lock = Lock()
_selected_backend: str | None = None
_INITIALIZATION_ERRORS = (InterfacingError, ImportError, OSError)


@dataclass(frozen=True)
class ModelStructure:
    """Invariant matrix and demand rows belonging to a single solver model."""

    inputs: ModelInputs
    variables: ModelVariables
    heat_balances: tuple[Constr, ...]


def update_model_demand(model: Model, inputs: ModelInputs) -> bool:
    """Update an identical model's heat demand and peak-dependent costs.

    Only the heat-balance RHS and objective depend on candidate demand.
    Require the remaining context data to be the same objects, so unrelated
    scenarios, technology changes, and different modes always rebuild.
    The solver retains its LP basis for exact reoptimization.
    """
    structure = getattr(model, "_heatgrid_structure", None)
    if not isinstance(structure, ModelStructure):
        return False
    previous = structure.inputs
    if (
        any(
            getattr(previous, name) is not getattr(inputs, name)
            for name in (
                "economic",
                "market",
                "technologies",
                "resources",
            )
        )
        or previous.options != inputs.options
    ):
        return False
    if any(
        getattr(previous.demand, field.name) is not getattr(inputs.demand, field.name)
        for field in fields(inputs.demand)
        if field.name != "demand_heat"
    ):
        return False
    inputs.validate()
    rhs = [
        float(inputs.demand.demand_heat[t] - inputs.demand.solar_heat[t])
        for t in range(len(structure.heat_balances))
    ]
    if model.solver_name == HIGHS and hasattr(model.solver, "update_heat_balances"):
        model.solver.update_heat_balances(structure.heat_balances, rhs)
    else:
        for constraint, value in zip(structure.heat_balances, rhs):
            constraint.rhs = value
    add_objective(model, inputs, structure.variables)
    model._heatgrid_structure = replace(structure, inputs=inputs)
    return True


def create_solver_model() -> Model:
    """Prefer Gurobi, falling back to bundled HiGHS if initialization fails.

    Remember the fallback within this process so parallel candidate models do
    not repeatedly try an unavailable library or license. Only initialization
    errors trigger fallback; model construction and solve errors propagate.
    """
    global _selected_backend
    with _solver_lock:
        if _selected_backend != HIGHS:
            try:
                model = Model(solver_name=GRB)
            except _INITIALIZATION_ERRORS as exc:
                LOGGER.warning("Gurobi could not initialize; using HiGHS instead: %s", exc)
                _selected_backend = HIGHS
            else:
                if _selected_backend is None:
                    LOGGER.info("Using optimization solver: Gurobi")
                _selected_backend = GRB
                return model
        try:
            model = Model(solver_name=HIGHS)
            if getattr(model, "solver_name", None) == HIGHS:
                from .highs_backend import HeatGridHighsSolver

                # Replace the empty backend before any variables are created.
                model.solver = HeatGridHighsSolver(model, "", model.sense)
                model.threads = 1
            return model
        except _INITIALIZATION_ERRORS as exc:
            raise RuntimeError(
                "HiGHS could not initialize after Gurobi was unavailable. "
                "Run 'uv sync' to install the bundled HiGHS solver dependencies."
            ) from exc


def selected_solver_backend() -> str | None:
    """Return the backend actually selected in this process, without probing."""
    return _selected_backend


def generate_deterministic_model_mip(inputs: ModelInputs) -> Model:
    """Create one validated solver model from typed model inputs."""

    inputs.validate()
    model = create_solver_model()
    variables = create_variables(model, inputs)
    # Objective construction and constraints are deliberately separate so each
    # mathematical responsibility can be characterized without changing this
    # public composition sequence.
    add_objective(model, inputs, variables)
    heat_balances = add_constraints(model, inputs, variables)
    model._heatgrid_structure = ModelStructure(inputs, variables, heat_balances)
    return model


__all__ = [
    "annuity_factor",
    "generate_deterministic_model_mip",
    "npv_factor",
]
