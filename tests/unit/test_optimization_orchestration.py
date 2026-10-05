import unittest
from unittest.mock import MagicMock, patch

import networkx as nx
import pandas as pd

from dh_compass.observability.progress import CancellationRequested, CancellationToken
from dh_compass.optimization.context import (
    ClusteringOptions,
    ContextDemandData,
    ContextMarketData,
    ContextTechnologyPortfolio,
    NetworkInputs,
    OptimizationResult,
    RuntimeServices,
)
from dh_compass.optimization.model_inputs import (
    EconomicInputs,
    MarketTimeSeries,
    ModelInputs,
    ModelOptions,
    ResourceLimits,
    TechnologyPortfolio,
)
from dh_compass.optimization.orchestration import (
    HeatGridOptimizer,
    OptimizationContext,
)


def _make_structured_ctx():
    n_steps = 8760
    profile = MagicMock(return_value=pd.Series([1.0] * n_steps))
    technology = {
        0: {
            "on_off": 0,
            "efficiency": 1.0,
            "efficiency_charge": 1.0,
            "efficiency_discharge": 1.0,
            "energy_to_power": 1.0,
            "power_to_heat_ratio": 1.0,
            "efficiency_electric": 1.0,
            "reinvest_factor": 0.0,
            "residual_value_factor": 0.0,
        }
    }
    portfolio = TechnologyPortfolio(
        battery_storage=technology,
        chp=technology,
        boiler=technology,
        heat_pump=technology,
        electrode_boiler=technology,
        heat_storage=technology,
        industrial_eh=technology,
        biomass_boiler=technology,
        biomass_chp=technology,
        waste_to_energy=technology,
        geothermal=technology,
        river_heat_pump=technology,
        wwtp_heat_pump=technology,
    )
    timestamps = pd.Series(range(n_steps))
    market = ContextMarketData(
        central=MarketTimeSeries(
            dt=1.0,
            timestamps=timestamps,
            fuel_price=[0.1] * n_steps,
            elec_price=[0.2] * n_steps,
            price_sell_pv=[0.05] * n_steps,
            price_sell_chp=[0.05] * n_steps,
            fuel_price_biomass=[0.05] * n_steps,
        ),
        decentral=MarketTimeSeries(
            dt=1.0,
            timestamps=timestamps,
            fuel_price=[0.1] * n_steps,
            elec_price=[0.2] * n_steps,
            price_sell_pv=[0.05] * n_steps,
            price_sell_chp=[0.05] * n_steps,
            fuel_price_biomass=[0.05] * n_steps,
        ),
    )
    return OptimizationContext(
        economic=EconomicInputs(0.05, 20, 0.02, 0.02, 0.0, 0.0, {}, {}, {}),
        market=market,
        demand=ContextDemandData(
            demand_electric=pd.Series([0.0] * n_steps),
            pv_infeed=pd.Series([0.0] * n_steps),
            solar_heat=[0.0] * n_steps,
            cop_decentral=[3.0] * n_steps,
            cop_central=[3.0] * n_steps,
            cop_central_river=[3.0] * n_steps,
            cop_central_wwtp=[3.0] * n_steps,
        ),
        technologies=ContextTechnologyPortfolio(portfolio, portfolio),
        resources=ResourceLimits(),
        options=ModelOptions(),
        network=NetworkInputs(100.0, 1.0, 0.0),
        runtime_services=RuntimeServices(lambda _: 0.0, lambda _: 0.0, lambda _: 0.0, profile),
        clustering=ClusteringOptions(),
    )


def _make_subgraph_df():
    return pd.DataFrame(
        [
            {
                "Subgraph ID": 10,
                "Total distribution pipe cost [€]": 1000,
                "Total building connection cost [€]": 500,
                "Total transfer station cost [€]": 200,
                "Total building count": 2,
                "Load Profile": {"load": pd.Series([10, 20] * 4380)},
                "Building Annual Demands [MWh/a]": [50.0, 60.0],
            },
            {
                "Subgraph ID": 20,
                "Total distribution pipe cost [€]": 2000,
                "Total building connection cost [€]": 1000,
                "Total transfer station cost [€]": 400,
                "Total building count": 3,
                "Load Profile": {"load": pd.Series([15, 25] * 4380)},
                "Building Annual Demands [MWh/a]": [40.0, 40.0, 70.0],
            },
        ]
    )


def _make_optimizer(ctx=None, subgraph_df=None):
    street_network = nx.Graph()
    street_network.add_node(1, x=7.0, y=51.0)
    street_network.add_node(2, x=7.1, y=51.1)
    street_network.add_node(3, x=7.2, y=51.2)
    street_network.add_edge(1, 2, length=100)
    street_network.add_edge(2, 3, length=100)
    subgraph_dict = {
        10: nx.Graph([(1, 2)]),
        20: nx.Graph([(3, 3)]),
    }
    return HeatGridOptimizer(
        context=ctx or _make_structured_ctx(),
        street_network=street_network,
        subgraph_dict=subgraph_dict,
        subgraph_attributes_df=subgraph_df or _make_subgraph_df(),
    )


class TestHeatGridOptimizer(unittest.TestCase):
    def test_live_snapshots_show_whole_candidates_and_only_accepted_paths(self):
        events = []

        class Observer:
            def emit(self, event_type, data=None):
                events.append((event_type, data))

        optimizer = _make_optimizer()
        optimizer.observer = Observer()
        optimizer.subgraph_dict[10].add_edge(2, 3)
        optimizer._candidate_started(10, 0, 2)
        started = events[-1][1]
        assert len(started["candidate_geojson"]["features"]) == 2
        assert len(started["candidate_network_geojson"]["features"]) == 3
        optimizer.state.connected_subgraphs = [10]
        optimizer.state.total_cost_central_cumulative = 100.0
        result = OptimizationResult(
            subgraph_id=10,
            central_cost=100.0,
            decentral_cost=200.0,
            is_connected=True,
            connection_length=100.0,
            grid_cost=0.0,
            connecting_path_nodes=[1, 2, 3],
        )
        optimizer._candidate_completed(result, index=0, total=2, duration_seconds=1.0)
        completed = events[-1][1]
        assert len(completed["candidate_geojson"]["features"]) == 2
        assert len(completed["connecting_path_geojson"]["features"]) == 1
        assert completed["central_cost_total"] == 100.0
        assert completed["marginal_central_cost"] == 100.0
        optimizer._candidate_started(20, 1, 2)
        rejected = OptimizationResult(
            subgraph_id=20,
            central_cost=300.0,
            decentral_cost=50.0,
            is_connected=False,
            connection_length=100.0,
            grid_cost=0.0,
            connecting_path_nodes=[1, 2, 3],
        )
        optimizer._candidate_completed(rejected, index=1, total=2, duration_seconds=1.0)
        assert events[-1][1]["connecting_path_geojson"]["features"] == []
        assert events[-1][1]["central_cost_total"] == 100.0
        assert events[-1][1]["marginal_central_cost"] == 200.0

    @patch("dh_compass.optimization.orchestration.generate_deterministic_model_mip")
    @patch("dh_compass.optimization.orchestration.gather_results_mip")
    @patch("dh_compass.optimization.orchestration.annuity_factor")
    def test_run_loop(self, mock_annuity, mock_gather, mock_gen):
        mock_annuity.return_value = 0.1
        mock_model = MagicMock()
        mock_model.objective_value = 5000.0
        mock_gen.return_value = mock_model
        mock_gather.return_value = (pd.DataFrame(), {})

        optimizer = _make_optimizer()
        results = optimizer.run([10, 20])

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].is_connected)
        self.assertEqual(results[0].subgraph_id, 10)

        stats = optimizer.perf.get_stats()
        self.assertIn("central_model_build_and_solve", stats)
        self.assertIn("total_optimization_loop", optimizer.perf.optimization_metrics)
        self.assertIn("central_solve_time_total", optimizer.perf.optimization_metrics)

    def test_candidate_events_and_cancellation_between_candidates(self):
        events = []

        class Observer:
            def emit(self, event_type, data=None):
                events.append((event_type, dict(data or {})))

        token = CancellationToken()
        optimizer = _make_optimizer()
        optimizer.observer = Observer()
        optimizer.cancellation_token = token
        result = OptimizationResult(
            subgraph_id=10,
            central_cost=10.0,
            decentral_cost=20.0,
            is_connected=True,
            connection_length=0.0,
            grid_cost=0.0,
        )

        def process(*_args, **_kwargs):
            token.cancel()
            return result

        with patch.object(optimizer, "process_subgraph", side_effect=process):
            with self.assertRaises(CancellationRequested):
                optimizer.run([10, 20])

        assert [event[0] for event in events] == [
            "optimization.candidate_started",
            "optimization.candidate_completed",
        ]
        assert events[-1][1]["completed_candidates"] == 1
        assert events[-1][1]["decision"] == "connected"
        assert events[-1][1]["provisional_geojson"] == {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[7.0, 51.0], [7.1, 51.1]],
            },
            "properties": {"candidate_id": 10, "decision": "connected"},
        }

    @patch("dh_compass.optimization.orchestration.generate_deterministic_model_mip")
    @patch("dh_compass.optimization.orchestration.gather_results_mip")
    def test_solve_single_cluster_sets_gurobi_threads(self, mock_gather, mock_gen):
        mock_model = MagicMock()
        mock_model.objective_value = 100.0
        mock_gen.return_value = mock_model

        optimizer = _make_optimizer(_make_structured_ctx())
        optimizer.cluster_solver.solve_one(
            0,
            {
                "centroid_demand": 50.0,
                "dominant_type": "EFH",
                "building_indices": [0],
                "total_demand": 50.0,
                "n_buildings": 1,
            },
            gurobi_threads=4,
        )

        self.assertEqual(mock_model.threads, 4)

    @patch("dh_compass.optimization.orchestration.generate_deterministic_model_mip")
    @patch("dh_compass.optimization.orchestration.gather_results_mip")
    def test_central_and_decentral_build_inputs_are_characterized(self, mock_gather, mock_gen):
        mock_model = MagicMock()
        mock_model.objective_value = 100.0
        mock_gen.return_value = mock_model
        mock_gather.return_value = (pd.DataFrame(), {})
        ctx = _make_structured_ctx()
        optimizer = _make_optimizer(ctx)
        demand = pd.Series([1.0] * 8760)

        optimizer.model_runner.run(demand, decentral=False)
        central = mock_gen.call_args_list[-1].args[0]
        optimizer.model_runner.run(demand, decentral=True)
        decentral = mock_gen.call_args_list[-1].args[0]
        optimizer.cluster_solver.solve_one(
            0,
            {
                "centroid_demand": 1.0,
                "dominant_type": "EFH",
                "building_indices": [0],
                "total_demand": 1.0,
                "n_buildings": 1,
            },
        )
        cluster = mock_gen.call_args_list[-1].args[0]

        assert all(isinstance(call.args[0], ModelInputs) for call in mock_gen.call_args_list)
        assert all(not call.kwargs for call in mock_gen.call_args_list)
        assert central.demand.demand_heat is demand
        assert central.market is ctx.market.central
        assert central.technologies is ctx.technologies.central
        assert central.options.decentral_bool == 0
        assert decentral.market is ctx.market.decentral
        assert decentral.technologies is ctx.technologies.decentral
        assert decentral.options.decentral_bool == 1
        assert (
            cluster.demand.demand_heat
            is ctx.runtime_services.building_profile_generator.return_value
        )
        assert cluster.options.decentral_bool == 1


class TestPerformanceMetrics(unittest.TestCase):
    @patch("dh_compass.optimization.orchestration.generate_deterministic_model_mip")
    @patch("dh_compass.optimization.orchestration.gather_results_mip")
    @patch("dh_compass.optimization.orchestration.annuity_factor")
    def test_per_cluster_metrics_sequential(self, mock_annuity, mock_gather, mock_gen):
        mock_annuity.return_value = 0.1
        mock_model = MagicMock()
        mock_model.objective_value = 5000.0
        mock_gen.return_value = mock_model
        mock_gather.return_value = (pd.DataFrame(), {})

        optimizer = _make_optimizer()
        optimizer.run([10])

        stats = optimizer.perf.get_stats()

        self.assertIn("decentral_model_build", stats)
        self.assertIn("decentral_model_solve", stats)
        self.assertIn("slp_generation", stats)
        self.assertIn("kmeans_clustering", stats)
        self.assertIn("central_model_build", stats)
        self.assertIn("central_model_solve", stats)

        n_clusters = stats["decentral_model_build_and_solve"]["count"]
        self.assertEqual(n_clusters, stats["decentral_model_build"]["count"])
        self.assertEqual(n_clusters, stats["decentral_model_solve"]["count"])

    @patch("dh_compass.optimization.orchestration.generate_deterministic_model_mip")
    @patch("dh_compass.optimization.orchestration.gather_results_mip")
    @patch("dh_compass.optimization.orchestration.annuity_factor")
    def test_per_cluster_metrics_parallel(self, mock_annuity, mock_gather, mock_gen):
        mock_annuity.return_value = 0.1
        mock_model = MagicMock()
        mock_model.objective_value = 5000.0
        mock_gen.return_value = mock_model
        mock_gather.return_value = (pd.DataFrame(), {})

        optimizer = _make_optimizer()
        optimizer.run([10, 20], max_workers=2)

        stats = optimizer.perf.get_stats()

        self.assertIn("decentral_model_build", stats)
        self.assertIn("decentral_model_solve", stats)
        self.assertIn("slp_generation", stats)
        self.assertIn("kmeans_clustering", stats)

        n_clusters = stats["decentral_model_build_and_solve"]["count"]
        self.assertEqual(n_clusters, stats["decentral_model_build"]["count"])
        self.assertEqual(n_clusters, stats["decentral_model_solve"]["count"])

        self.assertGreater(n_clusters, 0)

    @patch("dh_compass.optimization.orchestration.generate_deterministic_model_mip")
    @patch("dh_compass.optimization.orchestration.gather_results_mip")
    @patch("dh_compass.optimization.orchestration.annuity_factor")
    def test_cluster_count_metric(self, mock_annuity, mock_gather, mock_gen):
        mock_annuity.return_value = 0.1
        mock_model = MagicMock()
        mock_model.objective_value = 5000.0
        mock_gen.return_value = mock_model
        mock_gather.return_value = (pd.DataFrame(), {})

        optimizer = _make_optimizer()
        optimizer.run([10, 20])

        opt_metrics = optimizer.perf.optimization_metrics
        self.assertIn("cluster_count_subgraph_10", opt_metrics)
        self.assertIn("cluster_count_subgraph_20", opt_metrics)
        self.assertGreater(opt_metrics["cluster_count_subgraph_10"], 0)
        self.assertGreater(opt_metrics["cluster_count_subgraph_20"], 0)


if __name__ == "__main__":
    unittest.main()
