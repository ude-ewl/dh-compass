import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GridViewer } from "./GridViewer";
import { emptyNetwork, type GridStep } from "./viewerState";

vi.mock("../results/ResultMap", () => ({
  ResultMap: () => <div>Grid map</div>,
}));

it("shows only final results while retaining map playback for completed runs", async () => {
  render(
    <GridViewer
      finalResultsOnly
      title="Completed run"
      network={emptyNetwork}
      steps={[
        {
          candidateId: 1,
          decision: "connected",
          centralCost: 100,
          candidate: { id: 1, decision: "connected", buildings: 10 },
        },
      ]}
    >
      <div>Final combined grid</div>
    </GridViewer>,
  );
  expect(screen.getByText("Final combined grid")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "First step" }),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("Grid statistics")).not.toBeInTheDocument();
  expect(screen.queryByText("Costs for subgraph #1")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Subgraph details")).not.toBeInTheDocument();
});

it("follows new decisions, preserves a historical step, and returns to live", async () => {
  const user = userEvent.setup();
  const first: GridStep = { candidateId: 1, decision: "current" };
  const second: GridStep = { candidateId: 1, decision: "connected" };
  const third: GridStep = { candidateId: 2, decision: "current" };
  const props = { network: emptyNetwork, live: true, title: "Test run" };
  const { rerender } = render(<GridViewer {...props} steps={[first]} />);
  expect(screen.getByText("Step 1 / 1")).toBeInTheDocument();
  rerender(<GridViewer {...props} steps={[first, second]} />);
  expect(screen.getByText("Step 2 / 2")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "First step" }));
  rerender(<GridViewer {...props} steps={[first, second, third]} />);
  expect(screen.getByText("Step 1 / 3")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Follow live" })).toBeNull();
  expect(screen.queryByText(/Live grid|provisional|Viewing history/)).toBeNull();
  await user.click(screen.getByRole("button", { name: "Last step" }));
  expect(screen.getByText("Step 3 / 3")).toBeInTheDocument();
  expect(screen.getByText("Evaluating subgraph #2…")).toBeInTheDocument();
  rerender(<GridViewer {...props} steps={[first, second, third, second]} />);
  expect(screen.getByText("Step 4 / 4")).toBeInTheDocument();
});
