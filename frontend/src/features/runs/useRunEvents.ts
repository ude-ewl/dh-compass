import { useEffect, useRef, useState } from "react";

import { getRunEvents, runEventsUrl } from "../../api/client";
import type { RunEvent } from "../../api/workflow";
import { mergeRunEvents, runEventNames } from "./runEvents";

export type RunStreamState = "idle" | "connecting" | "live" | "interrupted";

export interface RunEventsResult {
  events: RunEvent[];
  streamState: RunStreamState;
  lastSequence: number;
}

const EMPTY: RunEventsResult = {
  events: [],
  streamState: "idle",
  lastSequence: 0,
};

const EVENT_SOURCE_OPEN = 1;
const EVENT_SOURCE_CLOSED = 2;

/**
 * Stream run events for immediacy, with ordered replay on (re)subscribe.
 *
 * Server-Sent Events are an optimization, not the source of truth: the run
 * resource is polled independently, so a closed stream only costs live detail
 * and is reported instead of replacing the workspace with an error. Replay
 * starts from the last observed sequence, which makes reconnects and refreshes
 * idempotent.
 */
export function useRunEvents(
  runId: string | undefined,
  enabled = true,
  stream = true,
): RunEventsResult {
  const [result, setResult] = useState<RunEventsResult>(EMPTY);
  const lastSequence = useRef(0);

  useEffect(() => {
    if (!runId || !enabled) {
      lastSequence.current = 0;
      setResult(EMPTY);
      return undefined;
    }
    let disposed = false;
    let source: EventSource | null = null;
    let recoveryTimer: ReturnType<typeof setTimeout> | null = null;
    let recoveryAttempt = 0;
    let handleMessage: ((message: MessageEvent<string>) => void) | null = null;
    const subscribedNames = new Set<string>();

    setResult({ events: [], streamState: "connecting", lastSequence: 0 });

    const clearRecoveryTimer = () => {
      if (recoveryTimer !== null) {
        clearTimeout(recoveryTimer);
        recoveryTimer = null;
      }
    };

    const replayAfterInterruption = () => {
      if (disposed) return;
      const delay = Math.min(1_000 * 2 ** recoveryAttempt, 10_000);
      recoveryAttempt += 1;
      clearRecoveryTimer();
      recoveryTimer = setTimeout(() => {
        recoveryTimer = null;
        void getRunEvents(runId, lastSequence.current)
          .then((replayed) => {
            if (disposed) return;
            apply(replayed);
            // EventSource normally reconnects itself. If construction failed
            // during an API restart there is no source to reconnect, so make a
            // fresh attempt after durable replay. Otherwise keep replaying on
            // bounded backoff until the existing stream opens.
            if (source === null) {
              connect(replayed);
            } else if (source.readyState !== EVENT_SOURCE_OPEN) {
              replayAfterInterruption();
            }
          })
          .catch(() => replayAfterInterruption());
      }, delay);
    };

    const subscribe = (name: string) => {
      if (!source || !handleMessage || subscribedNames.has(name)) return;
      source.addEventListener(name, handleMessage as EventListener);
      subscribedNames.add(name);
    };

    const apply = (incoming: RunEvent[]) => {
      if (disposed || incoming.length === 0) return;
      incoming.forEach((event) => subscribe(event.event_type));
      lastSequence.current = incoming.reduce(
        (highest, event) => Math.max(highest, event.sequence),
        lastSequence.current,
      );
      setResult((current) => {
        const events = mergeRunEvents(current.events, incoming);
        return events === current.events
          ? current
          : {
              events,
              streamState: current.streamState,
              lastSequence: lastSequence.current,
            };
      });
    };

    const connect = (observed: RunEvent[]) => {
      if (!stream) return;
      if (disposed || typeof window === "undefined") return;
      if (typeof window.EventSource !== "function") {
        // No streaming support in this environment. Polling keeps the run
        // workspace authoritative without an ever-failing stream banner.
        setResult((current) => ({
          ...current,
          streamState: current.streamState === "live" ? "live" : "connecting",
        }));
        return;
      }
      try {
        source = new EventSource(runEventsUrl(runId, lastSequence.current));
      } catch {
        source = null;
        setResult((current) => ({ ...current, streamState: "interrupted" }));
        replayAfterInterruption();
        return;
      }
      handleMessage = (message: MessageEvent<string>) => {
        try {
          apply([JSON.parse(message.data) as RunEvent]);
        } catch {
          // A malformed optional event must not take down the workspace.
        }
      };
      source.onopen = () => {
        if (disposed) return;
        recoveryAttempt = 0;
        clearRecoveryTimer();
        setResult((current) => ({ ...current, streamState: "live" }));
      };
      source.onerror = () => {
        if (disposed) return;
        setResult((current) => ({ ...current, streamState: "interrupted" }));
        if (source?.readyState === EVENT_SOURCE_CLOSED) {
          source.close();
          source = null;
        }
        replayAfterInterruption();
      };
      // Named SSE frames are only delivered to a listener for that exact
      // name, so the replay widens the subscription: an event type the backend
      // added after this build still reaches the activity feed.
      runEventNames(observed).forEach(subscribe);
    };

    void getRunEvents(runId, 0)
      .then((replayed) => {
        if (disposed) return;
        apply(replayed);
        connect(replayed);
      })
      .catch(() => {
        // Polling still restores the authoritative run state, so a failing
        // replay must not become a workspace-level error.
        connect([]);
      });

    return () => {
      disposed = true;
      clearRecoveryTimer();
      source?.close();
    };
  }, [enabled, runId, stream]);

  return result;
}
