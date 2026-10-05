"""Batched LP updates for the Python-MIP HiGHS backend.

Python-MIP's default objective setter clears every cost and then updates one
column at a time. HiGHS can apply the same full vector in one C API call.
This adapter remains behind Python-MIP's solver boundary, so construction and
result extraction use the existing mathematical model and variable API.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from mip import Constr, InterfacingError, LinExpr
from mip.highs import SolverHighs, check, ffi

LOGGER = logging.getLogger(__name__)


class HeatGridHighsSolver(SolverHighs):
    """HiGHS with exact bulk objective and equality-RHS updates."""

    normalization_scale = 1.0
    ipm_algorithm = "ipm"

    def _set_string_option_value(self, name, value):
        if name == "solver" and value == "ipm" and self.ipm_algorithm == "ipx_dual":
            try:
                super()._set_string_option_value(name, "ipx")
                self._set_int_option_value("ipx_dualize_strategy", 1)
                return
            except InterfacingError:
                LOGGER.warning("This HiGHS library cannot select dualized IPX; using default IPM")
        super()._set_string_option_value(name, value)

    def normalize(self, scale: float) -> None:
        """Express a fixed continuous LP in units of peak heat demand.

        With x = scale * z, A*z = b/scale and c*z has objective
        value f/scale. Keep costs/matrix unchanged and report x and f in
        physical units. Uniformly scaling all bounds also preserves storage
        intercepts, annual resource limits, and exogenous electric/solar loads.
        """
        if self.num_int():
            raise ValueError("LP normalization does not support integer variables")
        self._flush()
        scale = max(float(scale), 1.0)
        ratio = self.normalization_scale / scale
        if ratio == 1.0:
            return
        for rows, count in ((True, self.num_rows()), (False, self.num_cols())):
            if not count:
                continue
            lower = ffi.new("double[]", count)
            upper = ffi.new("double[]", count)
            actual = ffi.new("int*")
            nonzeros = ffi.new("int*")
            if rows:
                check(self._lib.Highs_getRowsByRange(
                    self._model, 0, count - 1, actual, lower, upper, nonzeros,
                    ffi.NULL, ffi.NULL, ffi.NULL,
                ))
            else:
                check(self._lib.Highs_getColsByRange(
                    self._model, 0, count - 1, actual, ffi.NULL, lower, upper,
                    nonzeros, ffi.NULL, ffi.NULL, ffi.NULL,
                ))
            for i in range(count):
                if abs(lower[i]) < 1e20:
                    lower[i] *= ratio
                if abs(upper[i]) < 1e20:
                    upper[i] *= ratio
            if rows:
                indices = ffi.new("int[]", list(range(count)))
                check(self._lib.Highs_changeRowsBoundsBySet(
                    self._model, count, indices, lower, upper,
                ))
            else:
                check(self._lib.Highs_changeColsBoundsByRange(
                    self._model, 0, count - 1, lower, upper,
                ))
        offset = super().get_objective_const() * ratio
        super().set_objective_const(offset)
        self.normalization_scale = scale

    def optimize(self, relax=False, lp_preprocess=False):
        self._x = []
        self._rc = []
        self._pi = []
        status = super().optimize(relax, lp_preprocess)
        self._x = [value * self.normalization_scale for value in self._x]
        return status

    def get_objective_value(self):
        value = super().get_objective_value()
        return None if value is None else value * self.normalization_scale

    def get_objective_bound(self):
        return super().get_objective_bound() * self.normalization_scale

    def get_objective_const(self):
        return super().get_objective_const() * self.normalization_scale

    def set_objective_const(self, value):
        super().set_objective_const(value / self.normalization_scale)

    def constr_get_rhs(self, index):
        return super().constr_get_rhs(index) * self.normalization_scale

    def constr_set_rhs(self, index, rhs):
        super().constr_set_rhs(index, rhs / self.normalization_scale)

    def constr_get_expr(self, constraint):
        expression = super().constr_get_expr(constraint)
        expression.const *= self.normalization_scale
        return expression

    def constr_get_slack(self, constraint):
        return super().constr_get_slack(constraint) * self.normalization_scale

    def var_get_lb(self, var):
        return super().var_get_lb(var) * self.normalization_scale

    def var_get_ub(self, var):
        return super().var_get_ub(var) * self.normalization_scale

    def var_set_lb(self, var, value):
        super().var_set_lb(var, value / self.normalization_scale)

    def var_set_ub(self, var, value):
        super().var_set_ub(var, value / self.normalization_scale)

    def set_objective(self, lin_expr: LinExpr, sense: str = "") -> None:
        self._flush()
        n = self.num_cols()
        if n:
            costs = ffi.new("double[]", n)
            for var, coefficient in lin_expr.expr.items():
                costs[var.idx] = coefficient
            check(self._lib.Highs_changeColsCostByRange(self._model, 0, n - 1, costs))
        self.set_objective_const(lin_expr.const)
        if lin_expr.sense:
            self.set_objective_sense(lin_expr.sense)
        elif sense:
            self.set_objective_sense(sense)

    def update_heat_balances(self, constraints: Sequence[Constr], values: Sequence[float]) -> None:
        self._flush()
        indices = ffi.new("int[]", [constraint.idx for constraint in constraints])
        bounds = ffi.new("double[]", [float(value) / self.normalization_scale for value in values])
        check(
            self._lib.Highs_changeRowsBoundsBySet(
                self._model,
                len(constraints),
                indices,
                bounds,
                bounds,
            )
        )
