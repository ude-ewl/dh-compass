import type { RunEvent, RunResource } from "../../api/workflow";
import {
  RUN_STAGES,
  canonicalStage,
  describeEvent,
  elapsedMs,
  extractFailureIssues,
  formatDuration,
  measuredFraction,
  mergeRunEvents,
  provisionalNetwork,
  runEventNames,
  stageLabel,
  stageStates,
  workerState,
} from "./runEvents";

function event(sequence: number, eventType: string, data = {}): RunEvent {
  return {
    id: `event-${sequence}`,
    run_id: "run-1",
    job_kind: "run",
    sequence,
    event_type: eventType,
    data,
    occurred_at: "2026-01-01T00:00:00Z",
  };
}

function run(overrides: Partial<RunResource> = {}): RunResource {
  return {
    id: "run-1",
    scenario_id: "scenario-1",
    scenario_revision_id: "revision-1",
    preview_id: null,
    name: "Study area run",
    description: null,
    output_label: null,
    status: "running",
    stage: "preparing_area",
    progress: null,
    candidate_progress: null,
    configuration_snapshot: {},
    configuration_version: "default-v1",
    bbox: [7.1, 51.2, 7.2, 51.3],
    data_snapshot: {},
    application_version: "0.1.0",
    solver_name: null,
    solver_version: null,
    process_identity: null,
    started_at: "2026-01-01T10:00:00Z",
    finished_at: null,
    created_at: "2026-01-01T09:59:00Z",
    updated_at: "2026-01-01T10:00:05Z",
    warnings: [],
    failure_summary: null,
    failure_details: {},
    artifacts: [],
    log_url: null,
    events_url: null,
    cancel_url: null,
    results_url: null,
    manifest_url: null,
    ...overrides,
  };
}

describe("run stage vocabulary", () => {
  it("maps worker and calculation stages onto one progression", () => {
    expect(canonicalStage("validate_datasets")).toBe("checking_input_data");
    expect(canonicalStage("assess_heat_resources")).toBe("finding_candidates");
    expect(canonicalStage("optimize_heat_grid")).toBe("optimizing_network");
    expect(canonicalStage("write_outputs")).toBe("preparing_results");
    expect(stageLabel(null)).toBe("Queued");
    expect(stageLabel("not_a_known_stage")).toBe("Not a known stage");
  });

  it("only marks stages the run has actually passed as done", () => {
    const states = stageStates("finding_candidates", "running");

    expect(states[0]).toBe("done");
    expect(states[1]).toBe("done");
    expect(states[2]).toBe("current");
    expect(states[3]).toBe("pending");
    expect(states).toHaveLength(RUN_STAGES.length);
  });

  it("never shows a completed progression for an unfinished run", () => {
    expect(
      stageStates(null, "queued").every((state) => state === "pending"),
    ).toBe(true);
    expect(stageStates("optimizing_network", "failed").at(-1)).toBe("pending");
    expect(
      stageStates("complete", "completed").every((s) => s === "done"),
    ).toBe(true);
  });
});

describe("progress measurement", () => {
  it("reports a percentage only when the backend measured one", () => {
    expect(measuredFraction(run())).toBeNull();
    expect(
      measuredFraction(
        run({
          progress: { stage: null, completed: 1, total: 2, fraction: null },
        }),
      ),
    ).toBeNull();
    expect(
      measuredFraction(
        run({
          progress: { stage: null, completed: 1, total: 2, fraction: 0.42 },
        }),
      ),
    ).toBeCloseTo(0.42);
  });

  it("counts elapsed time from the start and freezes after finishing", () => {
    const start = Date.parse("2026-01-01T10:00:00Z");

    expect(elapsedMs(run(), start + 65_000)).toBe(65_000);
    expect(
      elapsedMs(
        run({
          status: "completed",
          started_at: "2026-01-01T10:00:00Z",
          finished_at: "2026-01-01T10:02:30Z",
        }),
        start + 600_000,
      ),
    ).toBe(150_000);
  });

  it("counts a queued run from its creation", () => {
    expect(
      elapsedMs(
        run({
          status: "queued",
          started_at: null,
          created_at: "2026-01-01T10:00:00Z",
        }),
        Date.parse("2026-01-01T10:00:30Z"),
      ),
    ).toBe(30_000);
  });

  it("formats durations for reading at a glance", () => {
    expect(formatDuration(4_000)).toBe("4 s");
    expect(formatDuration(65_000)).toBe("1 m 05 s");
    expect(formatDuration(3_840_000)).toBe("1 h 04 m");
    expect(formatDuration(null)).toBe("—");
  });
});

describe("worker state", () => {
  const now = Date.parse("2026-01-01T10:00:30Z");

  it("separates waiting for a worker from a running worker", () => {
    expect(workerState(run({ status: "queued" }), now)?.label).toContain(
      "waiting for a worker",
    );
    expect(
      workerState(
        run({
          process_identity: {
            pid: 42,
            started_at: "2026-01-01T10:00:00Z",
            heartbeat_at: "2026-01-01T10:00:29Z",
          },
        }),
        now,
      )?.label,
    ).toBe("Worker running");
  });

  it("reports a delayed heartbeat instead of healthy work", () => {
    const state = workerState(
      run({
        process_identity: {
          pid: 42,
          started_at: "2026-01-01T10:00:00Z",
          heartbeat_at: "2026-01-01T09:50:00Z",
        },
      }),
      now,
    );

    expect(state?.tone).toBe("warning");
    expect(state?.label).toBe("Worker heartbeat is delayed");
  });

  it("reports a cancellation as a warning state", () => {
    expect(
      workerState(run({ status: "cancellation_requested" }), now)?.tone,
    ).toBe("warning");
  });

  it("has no worker state to show once the run is terminal", () => {
    expect(workerState(run({ status: "completed" }), now)).toBeNull();
  });
});

describe("event handling", () => {
  it("orders events and ignores duplicate replays", () => {
    const merged = mergeRunEvents(
      [event(2, "pipeline.stage_started", { stage: "preparing_area" })],
      [
        event(1, "job.status_changed", { status: "queued" }),
        event(2, "pipeline.stage_started", { stage: "preparing_area" }),
        event(3, "pipeline.stage_completed", { stage: "preparing_area" }),
      ],
    );

    expect(merged.map((item) => item.sequence)).toEqual([1, 2, 3]);
  });

  it("keeps heartbeats out of the visible feed", () => {
    expect(
      mergeRunEvents([], [event(1, "heartbeat", { status: "connected" })]),
    ).toEqual([]);
  });

  it("translates worker events into plain language", () => {
    expect(
      describeEvent(
        event(1, "pipeline.stage_started", { stage: "load_inputs" }),
      ),
    ).toBe("Started checking input data.");
    expect(
      describeEvent(
        event(2, "optimization.candidate_completed", {
          candidate_id: 7,
          decision: "connected",
        }),
      ),
    ).toBe("Candidate 7 was connected.");
  });

  it("translates the calculation lifecycle events it subscribes to", () => {
    // The calculation job emits these names, so an untranslated event would
    // reach the activity feed as an internal identifier.
    expect(
      describeEvent(
        event(1, "calculation.stage_started", { stage: "preparing_area" }),
      ),
    ).toBe("Started preparing area.");
    expect(
      describeEvent(
        event(2, "calculation.stage_completed", {
          stage: "finding_candidates",
        }),
      ),
    ).toBe("Completed finding candidates.");
  });

  it("never shows a raw event identifier for an unmodelled event", () => {
    expect(describeEvent(event(1, "solver.exceeded_time_limit", {}))).toBe(
      "Solver exceeded time limit.",
    );
    expect(describeEvent(event(2, "unheard_of_domain.unheard_of_event"))).toBe(
      "Unheard of domain unheard of event.",
    );
  });

  it("subscribes to the calculation lifecycle events", () => {
    const names = runEventNames();
    expect(names).toContain("calculation.stage_started");
    expect(names).toContain("calculation.stage_completed");
    expect(names).toContain("heartbeat");
  });

  it("widens the subscription with event names seen in replay", () => {
    // A backend event type added after this build must not be dropped: a named
    // SSE frame is only delivered to a listener for that exact name.
    const names = runEventNames([
      event(1, "future_domain.future_event"),
      event(2, "job.status_changed"),
    ]);
    expect(names).toContain("future_domain.future_event");
    expect(new Set(names).size).toBe(names.length);
  });

  it("collects only well-formed provisional network lines", () => {
    const network = provisionalNetwork([
      event(1, "optimization.candidate_completed", {
        candidate_id: 7,
        decision: "connected",
        provisional_geojson: {
          type: "Feature",
          geometry: {
            type: "LineString",
            coordinates: [
              [7, 51],
              [7.1, 51.1],
            ],
          },
          properties: { candidate_id: 7 },
        },
      }),
      event(2, "optimization.candidate_completed", {
        candidate_id: 8,
        provisional_geojson: { type: "Feature", geometry: null },
      }),
    ]);

    expect(network.features).toHaveLength(1);
  });
});

describe("failure details", () => {
  it("reads actionable issues and the diagnostic code", () => {
    expect(
      extractFailureIssues({
        code: "SOLVER_UNAVAILABLE",
        issues: [
          {
            message: "The solver is not installed.",
            remediation: "Install the configured solver.",
          },
          { not_a_message: true },
        ],
      }),
    ).toEqual([
      {
        message: "The solver is not installed.",
        remediation: "Install the configured solver.",
      },
    ]);
    expect(extractFailureIssues(null)).toEqual([]);
  });
});
