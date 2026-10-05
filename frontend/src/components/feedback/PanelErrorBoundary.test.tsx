import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import { PanelErrorBoundary } from "./PanelErrorBoundary";

describe("PanelErrorBoundary", () => {
  it("contains a render failure and offers a local retry", () => {
    function BrokenPanel(): ReactNode {
      throw new Error("fixture visualization failed");
    }

    render(
      <PanelErrorBoundary title="Network map">
        <BrokenPanel />
      </PanelErrorBoundary>,
    );

    expect(screen.getByText("Network map")).toBeInTheDocument();
    expect(screen.getByText("Retry panel")).toBeInTheDocument();
    expect(
      screen.queryByText("fixture visualization failed"),
    ).not.toBeVisible();

    fireEvent.click(screen.getByText("Technical details"));
    expect(screen.getByText("fixture visualization failed")).toBeVisible();
  });

  it("resets the failed child when the route-owned key changes", () => {
    function BrokenWhenRequested({ broken }: { broken: boolean }) {
      if (broken) throw new Error("broken");
      return <div>Recovered result</div>;
    }

    const { rerender } = render(
      <PanelErrorBoundary resetKey="run-1" title="Result panel">
        <BrokenWhenRequested broken />
      </PanelErrorBoundary>,
    );
    expect(screen.getByText("Retry panel")).toBeInTheDocument();

    rerender(
      <PanelErrorBoundary resetKey="run-2" title="Result panel">
        <BrokenWhenRequested broken={false} />
      </PanelErrorBoundary>,
    );
    expect(screen.getByText("Recovered result")).toBeInTheDocument();
  });
});
