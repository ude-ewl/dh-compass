import { render, screen } from "@testing-library/react";

import { KpiCards } from "./KpiCards";

describe("result KPI cards", () => {
  it("labels core overview values with units", () => {
    render(
      <KpiCards
        connectedBuildings={12}
        networkLength={345.6}
        peakLoad={78}
        summary={{
          connected_heat_demand_mwh: 1234.5,
          connected_share_pct: 67.8,
        }}
        totalCost={9000}
      />,
    );

    expect(screen.getByText("1 234.5 MWh/a")).toBeInTheDocument();
    expect(screen.getByText("9 000 €/a")).toBeInTheDocument();
    expect(screen.getByText("346 m")).toBeInTheDocument();
  });
});
