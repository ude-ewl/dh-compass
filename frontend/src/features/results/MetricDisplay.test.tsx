import { fireEvent, render, screen } from "@testing-library/react";

import { formatMetricValue, MetricDefinitionDisclosure } from "./MetricDisplay";

describe("metric contract display", () => {
  it("keeps annualized and capital cost units distinct", () => {
    expect(formatMetricValue("candidate.central_cost", 1_234)).toBe(
      "1\u202f234 €/a",
    );
    expect(formatMetricValue("candidate.central_grid_cost_raw", 1_234)).toBe(
      "1\u202f234 €",
    );
  });

  it("exposes scope, basis, stage, and provenance in a disclosure", () => {
    render(<MetricDefinitionDisclosure metric="candidate.central_cost" />);

    const disclosure = screen.getByText("Metric definition");
    expect(disclosure).toBeInTheDocument();
    expect(
      screen.queryByText("trial central connection of one candidate"),
    ).toBeNull();
    fireEvent.click(disclosure);
    expect(
      screen.getByText("trial central connection of one candidate"),
    ).toBeInTheDocument();
    expect(screen.getByText("candidate evaluation")).toBeInTheDocument();
  });
});
