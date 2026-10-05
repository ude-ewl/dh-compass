import { render, screen } from "@testing-library/react";

import {
  CostReconciliationNotice,
  reconcileAnnualizedCosts,
} from "./CostReconciliation";

describe("annualized cost reconciliation", () => {
  it("flags a mismatch beside the cost values", () => {
    render(
      <CostReconciliationNotice grid={600} supply={1_400} total={2_100} />,
    );

    expect(
      screen.getByText("Cost totals do not reconcile"),
    ).toBeInTheDocument();
    expect(screen.getByText(/difference is 100 €\/a/)).toBeInTheDocument();
  });

  it("does not flag rounded values within the tolerance", () => {
    expect(reconcileAnnualizedCosts(2_000.01, 1_400, 600)?.reconciles).toBe(
      true,
    );
    render(
      <CostReconciliationNotice grid={600} supply={1_400} total={2_000} />,
    );
    expect(screen.queryByText("Cost totals do not reconcile")).toBeNull();
  });
});
