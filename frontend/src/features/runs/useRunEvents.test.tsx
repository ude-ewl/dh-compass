import { render, screen, waitFor } from "@testing-library/react";
import { act } from "react";

import type { RunEvent } from "../../api/workflow";
import { useRunEvents } from "./useRunEvents";

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly listeners = new Map<
    string,
    Set<(message: MessageEvent<string>) => void>
  >();
  closed = false;
  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(
    name: string,
    handler: (message: MessageEvent<string>) => void,
  ) {
    const existing = this.listeners.get(name) ?? new Set();
    existing.add(handler);
    this.listeners.set(name, existing);
  }

  /** Names the client actually subscribed to. */
  listenerNames(): string[] {
    return [...this.listeners.keys()];
  }

  close() {
    this.closed = true;
    this.readyState = 2;
  }

  emit(name: string, payload: RunEvent) {
    for (const handler of this.listeners.get(name) ?? []) {
      handler({ data: JSON.stringify(payload) } as MessageEvent<string>);
    }
  }
}

function event(sequence: number, eventType: string): RunEvent {
  return {
    id: `event-${sequence}`,
    run_id: "run-1",
    job_kind: "run",
    sequence,
    event_type: eventType,
    data: { stage: "preparing_area", candidate_id: 7, decision: "connected" },
    occurred_at: "2026-01-01T00:00:00Z",
  };
}

function Probe({
  runId,
  enabled = true,
}: {
  runId?: string;
  enabled?: boolean;
}) {
  const { events, streamState, lastSequence } = useRunEvents(runId, enabled);
  return (
    <ul>
      <li>state: {streamState}</li>
      <li>last: {lastSequence}</li>
      {events.map((item) => (
        <li key={item.id}>
          #{item.sequence} {item.event_type}
        </li>
      ))}
    </ul>
  );
}

function stubReplay(payload: RunEvent[] | "reject") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/events")) {
        if (payload === "reject") {
          return new Response("boom", { status: 500 });
        }
        return new Response(JSON.stringify(payload), {
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("{}", {
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

describe("run event stream", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("replays stored events before opening the stream", async () => {
    stubReplay([
      event(1, "job.status_changed"),
      event(2, "pipeline.stage_started"),
    ]);

    render(<Probe runId="run-1" />);

    await screen.findByText("#1 job.status_changed");
    await waitFor(() => {
      expect(FakeEventSource.instances).toHaveLength(1);
    });
    // The stream resumes from the last replayed sequence.
    expect(FakeEventSource.instances[0].url).toContain("after_sequence=2");
  });

  it("appends streamed events and ignores replayed duplicates", async () => {
    stubReplay([event(1, "job.status_changed")]);
    render(<Probe runId="run-1" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];

    await act(async () => {
      source.emit(
        "optimization.candidate_completed",
        event(2, "optimization.candidate_completed"),
      );
      source.emit(
        "optimization.candidate_completed",
        event(2, "optimization.candidate_completed"),
      );
      source.emit("heartbeat", { ...event(1, "heartbeat") });
    });

    expect(
      screen.getByText("#2 optimization.candidate_completed"),
    ).toBeInTheDocument();
    expect(screen.queryByText("#1 heartbeat")).not.toBeInTheDocument();
  });

  it("reports an interruption without losing the events already received", async () => {
    stubReplay([event(1, "job.status_changed")]);
    render(<Probe runId="run-1" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];

    await act(async () => {
      source.onopen?.();
    });
    expect(screen.getByText("state: live")).toBeInTheDocument();

    await act(async () => {
      source.onerror?.();
    });

    expect(screen.getByText("state: interrupted")).toBeInTheDocument();
    // Recovering the live stream is an enhancement: the known events stay.
    expect(screen.getByText("#1 job.status_changed")).toBeInTheDocument();

    await act(async () => {
      source.onopen?.();
    });
    expect(screen.getByText("state: live")).toBeInTheDocument();
  });

  it("still opens a stream when the replay request fails", async () => {
    stubReplay("reject");

    render(<Probe runId="run-1" />);

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    expect(FakeEventSource.instances[0].url).toContain("after_sequence=0");
  });

  it("replays durably and reconnects when EventSource construction fails during an API restart", async () => {
    let constructionFailures = 1;
    vi.stubGlobal(
      "EventSource",
      class extends FakeEventSource {
        constructor(url: string) {
          if (constructionFailures > 0) {
            constructionFailures -= 1;
            throw new Error("API restarting");
          }
          super(url);
        }
      },
    );
    stubReplay([event(1, "job.status_changed")]);

    render(<Probe runId="run-1" />);
    await screen.findByText("#1 job.status_changed");
    expect(FakeEventSource.instances).toHaveLength(0);

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1), {
      timeout: 1_500,
    });
    expect(FakeEventSource.instances[0].url).toContain("after_sequence=1");
  });

  it("subscribes to the events the calculation lifecycle emits", async () => {
    stubReplay([event(1, "job.status_changed")]);
    render(<Probe runId="run-1" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const names = FakeEventSource.instances[0].listenerNames();

    expect(names).toContain("job.status_changed");
    expect(names).toContain("calculation.stage_started");
    expect(names).toContain("calculation.stage_completed");
    expect(names).toContain("optimization.candidate_completed");
  });

  it("subscribes to an event name it only learned from replay", async () => {
    // A named SSE frame for an unsubscribed type is discarded by the browser,
    // so replay widens the subscription instead of relying on a static list.
    stubReplay([event(1, "future_domain.future_event")]);
    render(<Probe runId="run-1" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    expect(FakeEventSource.instances[0].listenerNames()).toContain(
      "future_domain.future_event",
    );
  });

  it("closes the stream when the run is no longer live", async () => {
    stubReplay([]);
    const { rerender } = render(<Probe enabled runId="run-1" />);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    rerender(<Probe enabled={false} runId="run-1" />);

    await waitFor(() => expect(FakeEventSource.instances[0].closed).toBe(true));
    expect(screen.getByText("state: idle")).toBeInTheDocument();
  });
});
