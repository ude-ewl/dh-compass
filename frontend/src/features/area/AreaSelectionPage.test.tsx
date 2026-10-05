import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";

import type {
  CalculationAccepted,
  CalculationContract,
} from "../../api/calculations";
import { AreaSelectionPage } from "./AreaSelectionPage";

vi.mock("./BoundingBoxMap", () => ({
  BoundingBoxMap: ({
    bbox,
    onChange,
  }: {
    bbox: [number, number, number, number] | null;
    onChange: (bbox: [number, number, number, number]) => void;
  }) => (
    <>
      <output data-testid="map-bbox">{bbox?.join(",") ?? "none"}</output>
      <button onClick={() => onChange([7.1, 51.2, 7.2, 51.3])} type="button">
        Set map bbox
      </button>
    </>
  ),
}));

const contract: CalculationContract = {
  contract_version: "1",
  command: {
    method: "POST",
    path: "/api/v1/calculations",
    body: { bbox: ["west", "south", "east", "north"] },
    idempotency_header: "Idempotency-Key",
    idempotency: {
      same_key_same_bbox: "return_the_original_run",
      same_key_different_bbox: "409_IDEMPOTENCY_KEY_REUSED",
      preflight_rejection: "do_not_create_a_run",
      post_acceptance_failure: "preserve_failed_run_record",
    },
  },
  bbox: {
    crs: "EPSG:4326",
    coordinate_order: ["west", "south", "east", "north"],
    coverage_bbox: [5.866, 50.322, 9.531, 52.531],
    min_area_km2: 0.01,
    max_area_km2: 2_500,
    area_calculation: "approximate_wgs84_rectangle",
  },
  defaults: {
    configuration_version: "default-v1",
    source: "configs/default.toml",
    frontend_may_not_override: true,
  },
  lifecycle: {
    statuses: ["queued", "running", "completed", "failed", "cancelled"],
    terminal_statuses: ["completed", "failed", "cancelled"],
    response: {
      run_id: "opaque-run-id",
      status: "queued",
      status_url: "/api/v1/runs/opaque-run-id",
      bbox: ["west", "south", "east", "north"],
      configuration_version: "default-v1",
    },
  },
};

function renderPage(submitCalculation = vi.fn(), initialEntry = "/") {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(contract), {
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  return renderEntry(submitCalculation, initialEntry);
}

/** Render the page with a caller-controlled contract response. */
function renderEntry(
  submitCalculation: (
    bbox: [number, number, number, number],
    key: string,
  ) => Promise<CalculationAccepted>,
  initialEntry: string,
  contractResponse: () => Promise<Response> = async () =>
    new Response(JSON.stringify(contract), {
      headers: { "Content-Type": "application/json" },
    }),
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  vi.stubGlobal("fetch", vi.fn(contractResponse));
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AreaSelectionPage submitCalculation={submitCalculation} />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Expose the address so a consumed query parameter can be observed. */
function LocationProbe() {
  return <output data-testid="search">{useLocation().search}</output>;
}

describe("area selection workspace", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("keeps a search suggestion separate from the active area", async () => {
    const user = userEvent.setup();
    const submit = vi.fn();
    renderPage(submit);
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async (input) => {
      if (String(input).includes("/geocoding/search")) {
        return new Response(
          JSON.stringify({
            results: [
              {
                display_name: "Bad Oeynhausen",
                geometry: null,
                bbox: [7.1, 51.2, 7.2, 51.3],
                provider_id: "place-1",
              },
            ],
            provider: "test",
            warning: null,
          }),
          { headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify(contract), {
        headers: { "Content-Type": "application/json" },
      });
    });

    await user.type(
      screen.getByLabelText("Search for a place"),
      "Bad Oeynhausen",
    );
    await user.click(screen.getByRole("button", { name: "Search" }));
    await user.click(
      await screen.findByRole("option", { name: "Bad Oeynhausen" }),
    );

    expect(
      screen.getByText(/selected area was not changed/i),
    ).toBeInTheDocument();
    await user.click(screen.getByText("Exact extent"));
    await user.click(screen.getByRole("button", { name: "Use extent" }));
    expect(screen.getByRole("spinbutton", { name: "West" })).toHaveValue(7.1);
    expect(screen.getByRole("spinbutton", { name: "East" })).toHaveValue(7.2);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Start calculation" }),
      ).toBeEnabled();
    });
  });

  it("clears the map rectangle while an exact extent is invalid", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Set map bbox" }));
    await user.click(screen.getByText("Exact extent"));
    const west = screen.getByRole("spinbutton", { name: "West" });
    await user.clear(west);
    await user.type(west, "8");

    expect(screen.getByTestId("map-bbox")).toHaveTextContent("none");
    expect(
      screen.getByRole("button", { name: "Start calculation" }),
    ).toBeDisabled();
  });

  it("restores the rectangle handed back by an interrupted run", async () => {
    const submit = vi.fn();
    renderPage(submit, "/?bbox=7.1%2C51.2%2C7.2%2C51.3");

    // The active study area survives the trip to the run workspace.
    await waitFor(() => {
      expect(screen.getByTestId("map-bbox")).toHaveTextContent(
        "7.1,51.2,7.2,51.3",
      );
    });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Start calculation" }),
      ).toBeEnabled();
    });
  });

  it("ignores a rectangle handed back with invalid coordinates", async () => {
    renderPage(vi.fn(), "/?bbox=7.1,51.2");
    await waitFor(() => {
      expect(screen.getByTestId("map-bbox")).toHaveTextContent("none");
    });
    expect(
      screen.getByRole("button", { name: "Start calculation" }),
    ).toBeDisabled();
  });

  it("waits for the server limits before restoring a rectangle", async () => {
    // The client fallback allows 2500 km². Only the contract knows the real
    // maximum, so the hand-back must not be judged before it arrives.
    let releaseContract = () => {};
    const pending = new Promise<void>((resolve) => {
      releaseContract = resolve;
    });
    renderEntry(vi.fn(), "/?bbox=7.1%2C51.2%2C7.2%2C51.3", async () => {
      await pending;
      return new Response(
        JSON.stringify({
          ...contract,
          bbox: { ...contract.bbox, max_area_km2: 1 },
        }),
        { headers: { "Content-Type": "application/json" } },
      );
    });

    // Nothing is applied while the contract is still in flight.
    expect(screen.getByTestId("map-bbox")).toHaveTextContent("none");
    releaseContract();

    // The rectangle is far above the server maximum, so it stays unapplied.
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Start calculation" }),
      ).toBeDisabled();
    });
    expect(screen.getByTestId("map-bbox")).toHaveTextContent("none");
  });

  it("consumes the hand-back parameter once", async () => {
    renderPage(vi.fn(), "/?retry=1&bbox=7.1%2C51.2%2C7.2%2C51.3");

    await waitFor(() => {
      expect(screen.getByTestId("map-bbox")).toHaveTextContent(
        "7.1,51.2,7.2,51.3",
      );
    });
    // The rectangle is applied, and the address no longer carries it, so a
    // later visit or a browser Back cannot re-apply the same hand-back.
    expect(screen.getByTestId("search")).toHaveTextContent("");
  });
});
