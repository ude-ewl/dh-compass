import { render, screen } from "@testing-library/react";

import type { RunEvent } from "../../api/workflow";
import { ProvisionalRunMap } from "./RunMonitorPage";

const candidateCompleted: RunEvent = {
  id: "event-1",
  run_id: "run-1",
  job_kind: "run",
  sequence: 1,
  event_type: "optimization.candidate_completed",
  occurred_at: "2025-01-01T00:00:00Z",
  data: {
    candidate_id: 12,
    decision: "connected",
    provisional_geojson: {
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: [
          [7.0, 51.0],
          [7.1, 51.1],
        ],
      },
      properties: { candidate_id: 12, decision: "connected" },
    },
  },
};

describe("run monitor provisional map", () => {
  it("renders candidate geometry received in progress events", () => {
    render(<ProvisionalRunMap events={[candidateCompleted]} />);

    expect(
      screen.getByRole("region", { name: "Provisional network map" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Candidate 12" }),
    ).toBeInTheDocument();
  });
});
