import { render, screen } from "@testing-library/react";

import { CandidateInspector } from "./CandidateTable";

describe("candidate inspector", () => {
  it("converts full-results peak load from MW to a labelled kW value", () => {
    render(
      <CandidateInspector
        candidate={{
          id: 7,
          decision: "connected",
          peak_load_mw: 0.004,
        }}
      />,
    );

    expect(screen.getByText("4.0 kW")).toBeInTheDocument();
  });
});
