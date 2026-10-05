import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { RecentRunsPage } from "./RecentRunsPage";

function page(items: unknown[]) {
  return {
    items,
    pagination: {
      page: 1,
      page_size: 50,
      total: items.length,
      has_next: false,
      has_previous: false,
    },
  };
}

function renderPage(items: unknown[]) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      const body = JSON.stringify(page(items));
      return new Response(body, {
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RecentRunsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("recent runs recovery list", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists runs that can be reopened after a refresh", async () => {
    renderPage([
      {
        id: "run-1",
        name: "Bad Oeynhausen study area",
        status: "running",
        stage: "assess_heat_resources",
        bbox: [7.1, 51.2, 7.2, 51.3],
        started_at: "2026-01-01T10:00:00Z",
        finished_at: null,
        created_at: "2026-01-01T10:00:00Z",
        updated_at: "2026-01-01T10:00:30Z",
      },
      {
        id: "run-2",
        name: "Completed study area",
        status: "completed",
        stage: "complete",
        bbox: null,
        started_at: "2026-01-01T09:00:00Z",
        finished_at: "2026-01-01T09:04:00Z",
        created_at: "2026-01-01T09:00:00Z",
        updated_at: "2026-01-01T09:04:00Z",
      },
    ]);

    expect(
      await screen.findByText("Bad Oeynhausen study area"),
    ).toBeInTheDocument();
    // The current stage, not a fabricated completion claim.
    expect(screen.getByText(/Finding candidates/)).toBeInTheDocument();
    expect(screen.getByText(/^completed · 4 m 00 s/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open" })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "Open" })[0]).toHaveAttribute(
      "href",
      "/runs/run-1",
    );
  });

  it("offers the area selection when nothing has been calculated yet", async () => {
    renderPage([]);

    expect(await screen.findByText("No recent runs")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Select a study area" }),
    ).toHaveAttribute("href", "/");
  });
});
