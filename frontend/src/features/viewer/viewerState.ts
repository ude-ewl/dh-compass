import type {
  CandidateRecord,
  FeatureCollection,
  GeoJsonFeature,
  IterationRecord,
} from "../../api/results";
import type { RunEvent } from "../../api/workflow";

export type GridDecision = "pending" | "current" | "connected" | "rejected";
export interface GridStep {
  candidateId: number;
  decision: GridDecision;
  centralCost?: number;
  decentralCost?: number;
  cumulativeCost?: number;
  connectedDemand?: number;
  candidate?: CandidateRecord;
  path?: FeatureCollection | null;
}
export const emptyNetwork: FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

function collection(value: unknown): FeatureCollection | null {
  if (!value || typeof value !== "object") return null;
  const result = value as FeatureCollection;
  return result.type === "FeatureCollection" && Array.isArray(result.features)
    ? result
    : null;
}
function number(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
}

/** Replayed events and the live stream use the same geometry and decisions. */
export function liveGrid(events: RunEvent[]) {
  const steps: GridStep[] = [];
  const candidates = new Map<number, GeoJsonFeature[]>();
  for (const event of [...events].sort((a, b) => a.sequence - b.sequence)) {
    const data = event.data;
    const prepared = collection(data.candidate_network_geojson);
    for (const feature of prepared?.features ?? []) {
      const id = number(feature.properties?.candidate_id);
      if (id === undefined) continue;
      const features = candidates.get(id) ?? [];
      features.push(feature);
      candidates.set(id, features);
    }
    if (
      ![
        "optimization.candidate_started",
        "optimization.candidate_completed",
      ].includes(event.event_type)
    )
      continue;
    const id = number(data.candidate_id);
    if (id === undefined) continue;
    const completed = event.event_type === "optimization.candidate_completed";
    const decision = completed ? data.decision : "current";
    if (
      decision !== "current" &&
      decision !== "connected" &&
      decision !== "rejected"
    )
      continue;
    const geometry = collection(data.candidate_geojson);
    if (geometry) candidates.set(id, geometry.features);
    else if (!candidates.has(id) && data.provisional_geojson) {
      candidates.set(id, [data.provisional_geojson as GeoJsonFeature]);
    }
    steps.push({
      candidateId: id,
      decision,
      centralCost: number(data.marginal_central_cost),
      decentralCost: number(data.decentral_cost),
      cumulativeCost: number(data.central_cost_total),
      connectedDemand: number(data.connected_heat_demand_mwh),
      path:
        decision === "connected"
          ? collection(data.connecting_path_geojson)
          : null,
      candidate: completed
        ? {
            id,
            decision: decision as "connected" | "rejected",
            annual_heat_demand_mwh: number(data.annual_heat_demand_mwh),
            buildings: number(data.buildings),
            connection_length_m: number(data.connection_length_m),
            central_cost: number(data.marginal_central_cost),
            decentral_cost: number(data.decentral_cost),
          }
        : undefined,
    });
  }
  return {
    steps,
    network: {
      type: "FeatureCollection",
      features: [...candidates.values()].flat(),
    } as FeatureCollection,
  };
}

export function resultSteps(
  records: IterationRecord[],
  candidates: CandidateRecord[],
): GridStep[] {
  let acceptedCost: number | undefined;
  return records.map((record) => {
    if (record.decision === "connected")
      acceptedCost = record.central_cost_total;
    return {
      candidateId: record.subgraph_id,
      decision: record.decision,
      centralCost: record.marginal_central_cost,
      decentralCost: record.decentral_cost,
      cumulativeCost: acceptedCost ?? number(record.previous_central_cost),
      candidate: candidates.find(
        (candidate) => candidate.id === record.subgraph_id,
      ),
      path: record.connecting_path_geojson,
    };
  });
}

/** Future candidates stay pending; rejected paths never enter the growing grid. */
export function gridAtStep(
  network: FeatureCollection,
  steps: GridStep[],
  index: number,
  paths = emptyNetwork,
) {
  const observed = steps.slice(0, index + 1);
  const decisions = new Map<number, GridStep>();
  observed.forEach((step) => decisions.set(step.candidateId, step));
  const resolved = [...decisions.values()].filter(
    (step) => step.decision !== "current",
  );
  const connected = resolved.filter((step) => step.decision === "connected");
  const current = steps[index];
  const latestResolved = [...observed]
    .reverse()
    .find((step) => step.decision !== "current");
  const visiblePaths = paths.features.filter((feature) => {
    const id = number(
      feature.properties?.candidate_id ?? feature.properties?.subgraph_id,
    );
    const step = number(feature.properties?.step);
    return (
      feature.properties?.decision !== "rejected" &&
      (id !== undefined
        ? decisions.get(id)?.decision === "connected"
        : step !== undefined && step <= index)
    );
  });
  const reportedDemand = [...observed]
    .reverse()
    .find((step) => step.connectedDemand !== undefined)?.connectedDemand;
  const demandKnown = connected.every(
    (step) => step.candidate?.annual_heat_demand_mwh !== undefined,
  );
  return {
    current,
    connected: connected.length,
    rejected: resolved.filter((step) => step.decision === "rejected").length,
    cumulativeCost: latestResolved?.cumulativeCost,
    connectedDemand:
      reportedDemand ??
      (demandKnown
        ? connected.reduce(
            (sum, step) => sum + (step.candidate?.annual_heat_demand_mwh ?? 0),
            0,
          )
        : undefined),
    network: {
      ...network,
      features: network.features.map((feature) => ({
        ...feature,
        properties: {
          ...feature.properties,
          decision:
            decisions.get(Number(feature.properties?.candidate_id))?.decision ??
            "pending",
        },
      })),
    },
    paths: {
      type: "FeatureCollection",
      features: [
        ...(paths.features.length > 0
          ? visiblePaths
          : connected.flatMap((step) => step.path?.features ?? [])),
      ],
    } as FeatureCollection,
  };
}
