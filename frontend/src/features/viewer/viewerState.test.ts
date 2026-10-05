import type {
  FeatureCollection,
  GeoJsonFeature,
  IterationRecord,
} from "../../api/results";
import type { RunEvent } from "../../api/workflow";
import { gridAtStep, liveGrid, resultSteps } from "./viewerState";

const edge = (id: number): GeoJsonFeature => ({
  type: "Feature",
  geometry: {
    type: "LineString",
    coordinates: [
      [7, 51],
      [7.01, 51.01],
    ],
  },
  properties: { candidate_id: id },
});
const network: FeatureCollection = {
  type: "FeatureCollection",
  features: [edge(1), edge(1), edge(2), edge(3)],
};
const event = (
  sequence: number,
  event_type: string,
  data: Record<string, unknown>,
): RunEvent => ({
  id: `event-${sequence}`,
  run_id: "run-1",
  job_kind: "run",
  sequence,
  event_type,
  data,
  occurred_at: "2026-10-04T10:00:00Z",
});
const events = [
  event(1, "optimization.candidate_started", {
    candidate_id: 1,
    candidate_network_geojson: network,
  }),
  event(2, "optimization.candidate_completed", {
    candidate_id: 1,
    decision: "connected",
    marginal_central_cost: 100,
    central_cost_total: 100,
    connected_heat_demand_mwh: 12,
  }),
  event(3, "optimization.candidate_started", { candidate_id: 2 }),
  event(4, "optimization.candidate_completed", {
    candidate_id: 2,
    decision: "rejected",
    central_cost_total: 100,
    connecting_path_geojson: { type: "FeatureCollection", features: [edge(2)] },
  }),
  event(5, "optimization.candidate_started", { candidate_id: 3 }),
  event(6, "optimization.candidate_completed", {
    candidate_id: 3,
    decision: "connected",
    central_cost_total: 150,
    connecting_path_geojson: { type: "FeatureCollection", features: [edge(3)] },
  }),
];

describe("live grid history", () => {
  it("retains complete subgraphs, evaluates one, and keeps future candidates pending", () => {
    const grid = liveGrid(events);
    const snapshot = gridAtStep(grid.network, grid.steps, 2);
    expect(
      snapshot.network.features.map((feature) => feature.properties?.decision),
    ).toEqual(["connected", "connected", "current", "pending"]);
    expect(snapshot.connected).toBe(1);
    expect(snapshot.rejected).toBe(0);
    expect(snapshot.connectedDemand).toBe(12);
  });
  it("only grows accepted paths, with no future or rejected connections in replay", () => {
    const grid = liveGrid(events);
    expect(gridAtStep(grid.network, grid.steps, 3).paths.features).toEqual([]);
    const final = gridAtStep(grid.network, grid.steps, 5);
    expect(final.paths.features).toEqual([edge(3)]);
    expect(final.connected).toBe(2);
    expect(final.rejected).toBe(1);
    expect(final.cumulativeCost).toBe(150);
  });
  it("does not count a started and completed event as two candidates", () => {
    const grid = liveGrid(events);
    expect(gridAtStep(grid.network, grid.steps, 5).connected).toBe(2);
    expect(grid.steps[1].centralCost).toBe(100);
  });
  it("uses accepted cumulative costs during final replay and filters paths by candidate", () => {
    const records: IterationRecord[] = [
      {
        step: 0,
        subgraph_id: 1,
        decision: "connected",
        central_cost_total: 100,
      },
      {
        step: 1,
        subgraph_id: 2,
        decision: "rejected",
        central_cost_total: 300,
        previous_central_cost: 100,
      },
      {
        step: 2,
        subgraph_id: 3,
        decision: "connected",
        central_cost_total: 150,
      },
    ];
    const paths: FeatureCollection = {
      type: "FeatureCollection",
      features: [edge(2), edge(3)],
    };
    const steps = resultSteps(records, []);
    expect(gridAtStep(network, steps, 1, paths).paths.features).toEqual([]);
    expect(gridAtStep(network, steps, 1).cumulativeCost).toBe(100);
    expect(gridAtStep(network, steps, 2, paths).paths.features).toEqual([
      edge(3),
    ]);
  });
  it("does not duplicate an accepted path available from both artifacts", () => {
    const path: FeatureCollection = {
      type: "FeatureCollection",
      features: [edge(1)],
    };
    expect(
      gridAtStep(
        network,
        [{ candidateId: 1, decision: "connected", path }],
        0,
        path,
      ).paths.features,
    ).toHaveLength(1);
  });
});
