import { fireEvent, render, screen } from "@testing-library/react";

import type { FeatureCollection } from "../../api/results";
import { ResultMap } from "./ResultMap";

const MAX_MAP_FEATURES = 10_000;

const candidateNetwork: FeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: [
          [7, 51],
          [7.1, 51.1],
        ],
      },
      properties: { candidate_id: 7, decision: "connected" },
    },
  ],
};

describe("result map", () => {
  it("provides an accessible fallback layer and selects a candidate", () => {
    const onSelect = vi.fn();
    render(
      <ResultMap
        candidateNetwork={candidateNetwork}
        onSelectCandidate={onSelect}
      />,
    );

    expect(
      screen.getByRole("img", { name: "Heat network result map" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Candidate 7" }));
    expect(onSelect).toHaveBeenCalledWith(7);
  });

  it("bounds large layers and explains that the candidate table remains complete", () => {
    const features = Array.from(
      { length: MAX_MAP_FEATURES + 1 },
      () => candidateNetwork.features[0],
    );
    render(
      <ResultMap
        candidateNetwork={{ type: "FeatureCollection", features }}
        showCandidates={false}
      />,
    );

    expect(screen.getByText(/Map display is limited/)).toHaveTextContent(
      `first ${"10 000"}`,
    );
    expect(screen.getByText(/Map display is limited/)).toHaveTextContent(
      "The candidate table remains complete.",
    );
  });

  it("skips malformed features instead of passing them to the map", () => {
    render(
      <ResultMap
        candidateNetwork={{
          type: "FeatureCollection",
          features: [
            candidateNetwork.features[0],
            {
              type: "Feature",
              geometry: {
                type: "LineString",
                coordinates: [[7, Number.NaN]],
              },
              properties: {},
            },
          ],
        }}
      />,
    );

    expect(screen.getByText(/Map display is limited/)).toHaveTextContent(
      "Candidate areas skipped 1 malformed features",
    );
    expect(
      screen.getByRole("button", { name: "Candidate 7" }),
    ).toBeInTheDocument();
  });
});
