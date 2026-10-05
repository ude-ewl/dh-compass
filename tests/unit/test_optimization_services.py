from types import SimpleNamespace

import networkx as nx
import pandas as pd
import pytest
from mip import MipBaseException

from dh_compass.optimization.candidate_evaluator import CandidateEvaluator
from dh_compass.optimization.cluster_solver import ClusterSolver, ClusterSolveRecord
from dh_compass.optimization.connection_evaluator import ConnectionEvaluator
from dh_compass.optimization.model_runner import ModelRun, ModelRunTiming
from dh_compass.optimization.result_extraction import ModelSolution
from dh_compass.optimization.run_state import IterationRecord, OptimizationRunState


def _network_context():
    return SimpleNamespace(
        network=SimpleNamespace(
            infrastructure_cost_factor=1.0,
            pipeline_cost_per_m=10.0,
            residual_value_factor_pipeline=0.0,
        ),
        runtime_services=SimpleNamespace(pump_cost_func=lambda peak: peak * 2.0),
        clustering=SimpleNamespace(n_clusters=5, random_state=42),
    )


def test_connection_evaluator_returns_shortest_path_and_raw_cost():
    network = nx.Graph()
    network.add_edge(1, 2, length=3.0)
    network.add_edge(2, 3, length=4.0)
    subgraphs = {10: nx.Graph([(1, 1)]), 20: nx.Graph([(3, 3)])}
    attributes = pd.DataFrame(
        [
            {
                "Subgraph ID": 10,
                "Total distribution pipe cost [€]": 10.0,
                "Total building connection cost [€]": 20.0,
                "Total transfer station cost [€]": 30.0,
            },
            {
                "Subgraph ID": 20,
                "Total distribution pipe cost [€]": 40.0,
                "Total building connection cost [€]": 50.0,
                "Total transfer station cost [€]": 60.0,
            },
        ]
    ).set_index("Subgraph ID")
    evaluator = ConnectionEvaluator(
        network,
        subgraphs,
        attributes,
        _network_context(),
    )

    connection = evaluator.find_shortest_connection(20, [10])

    assert connection.path == [1, 2, 3]
    assert connection.length == 7.0
    assert evaluator.get_subgraph_grid_cost(20) == 150.0


def test_candidate_evaluator_updates_explicit_state():
    context = _network_context()
    attributes = pd.DataFrame(
        [
            {
                "Subgraph ID": 1,
                "Load Profile": {"load": pd.Series([1.0, 2.0])},
                "Building Annual Demands [MWh/a]": [10.0],
                "Total distribution pipe cost [€]": 10.0,
                "Total building connection cost [€]": 20.0,
                "Total transfer station cost [€]": 30.0,
            }
        ]
    ).set_index("Subgraph ID")
    connection_evaluator = ConnectionEvaluator(
        nx.Graph(),
        {1: nx.Graph([(1, 1)])},
        attributes,
        context,
    )

    class FakeRunner:
        def run(self, *args, **kwargs):
            return ModelRun(100.0, ModelSolution(), ModelRunTiming(0.1, 0.2))

    class FakeClusters:
        def solve(self, clusters, *, max_workers=None):
            return 20.0, {}

    state = OptimizationRunState()
    evaluator = CandidateEvaluator(
        context,
        attributes,
        model_runner=FakeRunner(),
        cluster_solver=FakeClusters(),
        connection_evaluator=connection_evaluator,
        annuity_factor_value=1.0,
    )

    evaluation = evaluator.evaluate(1, state, is_first=True)

    assert evaluation.result.is_connected
    assert state.connected_subgraphs == [1]
    assert state.demand_heat_cumulative.equals(pd.Series([1.0, 2.0]))
    assert evaluation.result.central_cost == 164.0


def test_parallel_cluster_failure_falls_back_to_sequential():
    solver = ClusterSolver(SimpleNamespace())
    calls = []

    def fake_solve_one(cluster_id, cluster_info, *, gurobi_threads=None):
        calls.append((cluster_id, gurobi_threads))
        if cluster_id == 1 and gurobi_threads is not None:
            raise MipBaseException("worker failure")
        return ClusterSolveRecord(
            cluster_id=cluster_id,
            obj_val=cluster_id + 1.0,
            centroid_demand=10.0,
            total_demand=10.0,
            n_buildings=1,
            scaled_cost=cluster_id + 1.0,
        )

    solver.solve_one = fake_solve_one
    clusters = {
        0: {"building_indices": [0]},
        1: {"building_indices": [1]},
    }

    total_cost, details = solver.solve(clusters, max_workers=2)

    assert total_cost == 3.0
    assert set(details) == {0, 1}
    assert (1, None) in calls


def test_parallel_cluster_programming_error_is_not_retried():
    solver = ClusterSolver(SimpleNamespace())
    calls = []

    def fake_solve_one(cluster_id, cluster_info, *, gurobi_threads=None):
        calls.append((cluster_id, gurobi_threads))
        raise RuntimeError("invalid cluster implementation")

    solver.solve_one = fake_solve_one

    with pytest.raises(RuntimeError, match="invalid cluster implementation"):
        solver.solve({1: {"building_indices": [0]}}, max_workers=2)

    assert len(calls) == 1
    assert calls[0][1] is not None


def test_iteration_record_is_typed_and_serializable():
    record = IterationRecord(
        step=0,
        subgraph_id=3,
        decision="connected",
        central_cost_total=10.0,
        previous_central_cost=0.0,
        marginal_central_cost=10.0,
        decentral_cost=12.0,
        grid_cost_raw=5.0,
        connection_length_m=0.0,
        cumulative_connected_ids=[3],
        connecting_path_nodes=None,
    )

    assert record.subgraph_id == 3
    assert record.central_cost_total == 10.0
    assert record.decision == "connected"
