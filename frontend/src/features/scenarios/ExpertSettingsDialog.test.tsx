import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type {
  ConfigurationField,
  ConfigurationSchemaResponse,
} from "../../api/projects";
import { ExpertSettingsDialog } from "./ExpertSettingsDialog";

const mocks = vi.hoisted(() => ({
  updateScenarioConfig: vi.fn(),
  validateScenarioConfig: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  ApiClientError: class ApiClientError extends Error {},
  updateScenarioConfig: mocks.updateScenarioConfig,
  validateScenarioConfig: mocks.validateScenarioConfig,
}));

const thresholdField: ConfigurationField = {
  key: "network.linear_heat_density_threshold",
  section: "network",
  section_label: "Network",
  group: "network",
  group_label: "Network",
  label: "Linear heat density threshold",
  description: "Threshold",
  data_type: "number",
  unit: "MWh/(m·a)",
  default: 2,
  has_default: true,
  value: 2,
  changed_from_default: false,
  changed_from_parent: false,
  expert_only: false,
  editable: true,
  runtime_only: false,
  impact: "preview",
  preprocessing_impact: true,
  sensitive: false,
  path_policy: null,
  constraints: { minimum: 0 },
};

const costCurveField: ConfigurationField = {
  ...thresholdField,
  key: "economics.cost_structures.chp.300",
  section: "economics",
  section_label: "Economics",
  group: "cost_curves",
  group_label: "Cost curves",
  label: "300",
  default: 1017,
  value: 1017,
  impact: "run",
  preprocessing_impact: false,
};

const schema: ConfigurationSchemaResponse = {
  version: "1",
  fields: [thresholdField, costCurveField],
};

vi.mock("../../api/queries", () => ({
  useConfigurationSchemaQuery: () => ({
    data: schema,
    isError: false,
  }),
}));

vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useBlocker: () => ({ state: "unblocked" }),
}));

describe("ExpertSettingsDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("restores renamed cost-curve thresholds when resetting a section", async () => {
    const user = userEvent.setup();
    render(
      <ExpertSettingsDialog
        document={{ economics: { cost_structures: { chp: { 300: 1017 } } } }}
        onApplied={vi.fn()}
        onClose={vi.fn()}
        open
        revisionId="revision-1"
        scenarioId="scenario-1"
      />,
    );

    await user.click(screen.getByRole("button", { name: /Cost curves/ }));
    const table = screen.getByRole("table", {
      name: "economics.cost_structures.chp cost curve",
    });
    const threshold = within(table).getAllByRole("spinbutton")[0];
    await user.clear(threshold);
    await user.type(threshold, "350");
    await user.click(screen.getByRole("button", { name: "Reset section" }));

    expect(within(table).getAllByRole("spinbutton")).toHaveLength(2);
    expect(within(table).getAllByRole("spinbutton")[0]).toHaveValue(300);
  });

  it("requires a second Apply confirmation when a preview will be invalidated", async () => {
    const user = userEvent.setup();
    const document = { network: { linear_heat_density_threshold: 2 } };
    const validated = {
      valid: true,
      document: { network: { linear_heat_density_threshold: 3 } },
      changed_paths: ["network.linear_heat_density_threshold"],
      changed_from_default: ["network.linear_heat_density_threshold"],
      changed_from_parent: ["network.linear_heat_density_threshold"],
      field_errors: [],
      warnings: [],
      invalidation: {
        effect: "preview_invalidated" as const,
        changed_paths: ["network.linear_heat_density_threshold"],
        preview_paths: ["network.linear_heat_density_threshold"],
        run_only_paths: [],
        no_impact_paths: [],
        preview_invalidated: true,
        new_run_required: true,
        run_only_change: false,
        reasons: [],
      },
    };
    mocks.validateScenarioConfig.mockResolvedValue(validated);
    mocks.updateScenarioConfig.mockResolvedValue({});

    render(
      <ExpertSettingsDialog
        document={document}
        onApplied={vi.fn()}
        onClose={vi.fn()}
        open
        revisionId="revision-1"
        scenarioId="scenario-1"
      />,
    );

    const input = screen.getByRole("spinbutton", {
      name: "Linear heat density threshold",
    });
    await user.clear(input);
    await user.type(input, "3");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(
      await screen.findByText("Preview invalidation requires confirmation."),
    ).toBeInTheDocument();
    expect(mocks.updateScenarioConfig).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Apply again" }));
    await waitFor(() =>
      expect(mocks.updateScenarioConfig).toHaveBeenCalledTimes(1),
    );
  });
});
