from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from mip import GRB, HIGHS, InterfacingError

from dh_compass.optimization import model


@pytest.fixture(autouse=True)
def reset_backend(monkeypatch):
    monkeypatch.setattr(model, "_selected_backend", None)


def test_usable_gurobi_remains_preferred(monkeypatch):
    factory = Mock(return_value=object())
    monkeypatch.setattr(model, "Model", factory)
    assert model.create_solver_model() is factory.return_value
    assert model.create_solver_model() is factory.return_value
    assert [call.kwargs["solver_name"] for call in factory.call_args_list] == [GRB, GRB]
    assert model.selected_solver_backend() == GRB


@pytest.mark.parametrize("error", [
    InterfacingError("Gurobi environment could not be loaded, check your license."),
    FileNotFoundError("Gurobi library missing"),
    ImportError("Gurobi unavailable"),
    OSError("Gurobi library could not load"),
])
def test_initialization_failure_falls_back_and_is_remembered(monkeypatch, caplog, error):
    highs = object()
    factory = Mock(side_effect=[error, highs, highs])
    monkeypatch.setattr(model, "Model", factory)
    assert model.create_solver_model() is highs
    assert model.create_solver_model() is highs
    assert [call.kwargs["solver_name"] for call in factory.call_args_list] == [GRB, HIGHS, HIGHS]
    assert model.selected_solver_backend() == HIGHS
    assert "using HiGHS instead" in caplog.text


def test_parallel_models_attempt_unavailable_gurobi_only_once(monkeypatch):
    factory = Mock(side_effect=lambda *, solver_name: (
        (_ for _ in ()).throw(InterfacingError("No license"))
        if solver_name == GRB else object()
    ))
    monkeypatch.setattr(model, "Model", factory)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: model.create_solver_model(), range(8)))
    names = [call.kwargs["solver_name"] for call in factory.call_args_list]
    assert len(results) == 8
    assert names.count(GRB) == 1
    assert names.count(HIGHS) == 8


def test_other_errors_do_not_trigger_fallback(monkeypatch):
    factory = Mock(side_effect=ValueError("Invalid model input"))
    monkeypatch.setattr(model, "Model", factory)
    with pytest.raises(ValueError, match="Invalid model"):
        model.create_solver_model()
    factory.assert_called_once_with(solver_name=GRB)


def test_missing_highs_explains_how_to_install(monkeypatch):
    monkeypatch.setattr(model, "Model", Mock(side_effect=[
        InterfacingError("No license"), FileNotFoundError("No HiGHS library"),
    ]))
    with pytest.raises(RuntimeError, match="uv sync") as error:
        model.create_solver_model()
    assert isinstance(error.value.__cause__, FileNotFoundError)


def test_gurobi_can_become_unavailable_after_a_successful_initialization(monkeypatch):
    gurobi, highs = object(), object()
    monkeypatch.setattr(model, "Model", Mock(side_effect=[
        gurobi, InterfacingError("License unavailable"), highs,
    ]))
    assert model.create_solver_model() is gurobi
    assert model.create_solver_model() is highs


def test_real_highs_fallback_solves_an_integer_problem(monkeypatch):
    from mip import INTEGER, Model, OptimizationStatus

    def factory(*, solver_name):
        if solver_name == GRB:
            raise InterfacingError("Simulated unavailable Gurobi license")
        return Model(solver_name=solver_name)

    monkeypatch.setattr(model, "Model", factory)
    problem = model.create_solver_model()
    problem.verbose = 0
    quantity = problem.add_var(var_type=INTEGER, lb=0)
    problem += quantity >= 1.2
    problem.objective = quantity
    assert problem.optimize() == OptimizationStatus.OPTIMAL
    assert quantity.x == pytest.approx(2)
    assert model.selected_solver_backend() == HIGHS
