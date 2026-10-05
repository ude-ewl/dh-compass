import { render, screen } from "@testing-library/react";

import type { DatasetDescriptor, DatasetReadiness } from "../../api/workflow";
import { DataStep } from "./DataStep";

const building: DatasetDescriptor = {
  id: "buildings",
  label: "Building demand data",
  description: "Heated building geometries and annual demand attributes.",
  required: true,
  status: "invalid",
  path_display: "data/buildings.gpkg",
  format: "GeoPackage",
  layer: null,
  columns: [],
  crs: null,
  extent: null,
  metadata: {},
  issues: [
    {
      severity: "error",
      code: "DATASET_SCHEMA_INVALID",
      message: "A required column is missing.",
      remediation: "Provide a compatible building dataset.",
    },
  ],
  actions: [],
  checked_at: "2026-01-01T00:00:00Z",
};

const biomass: DatasetDescriptor = {
  ...building,
  id: "biomass",
  label: "Biomass potential",
  description: "Optional location-dependent resource potential.",
  required: true,
  status: "ready",
  issues: [
    {
      severity: "warning",
      code: "RESOURCE_OUTSIDE_STUDY_AREA",
      message: "Biomass potential does not cover the selected area.",
      remediation: "It will not be used in this area.",
    },
  ],
};

const timeSeries: DatasetDescriptor = {
  ...building,
  id: "time_series",
  label: "Demand time series",
  status: "ready",
  issues: [],
};

const readiness: DatasetReadiness = {
  scenario_id: "scenario-1",
  ready: false,
  checked_at: "2026-01-01T00:00:00Z",
  datasets: [building, biomass, timeSeries],
  blocking_issues: building.issues,
};

vi.mock("@tanstack/react-query", () => ({
  useMutation: () => ({ isPending: false, isError: false, mutate: vi.fn() }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("../../api/queries", () => ({
  useDatasetLayerQuery: () => ({
    data: undefined,
    isPending: false,
    isError: false,
  }),
  useDatasetsQuery: () => ({
    data: readiness,
    isPending: false,
    isError: false,
  }),
}));

describe("DataStep", () => {
  it("separates blocking inputs from non-blocking coverage notices", () => {
    render(<DataStep scenarioId="scenario-1" />);

    expect(
      screen.getByRole("heading", { name: "Blocking inputs (1)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Coverage notices (1)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Enabled resource · GeoPackage"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Needs attention (2)")).not.toBeInTheDocument();
  });
});
