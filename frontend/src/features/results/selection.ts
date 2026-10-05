import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

function integerParam(value: string | null): number | null {
  if (value === null || !/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

/**
 * Result selections live in the URL so a candidate or playback step can be
 * bookmarked, refreshed, and shared between the map, table, and inspector.
 */
export function useResultSelection() {
  const [params, setParams] = useSearchParams();
  const candidateId = integerParam(params.get("candidate"));
  const iterationIndex = integerParam(params.get("iteration"));

  const update = useCallback(
    (updates: { candidate?: number | null; iteration?: number | null }) => {
      const next = new URLSearchParams(params);
      if ("candidate" in updates) {
        if (updates.candidate === null || updates.candidate === undefined) {
          next.delete("candidate");
        } else {
          next.set("candidate", String(updates.candidate));
        }
      }
      if ("iteration" in updates) {
        if (updates.iteration === null || updates.iteration === undefined) {
          next.delete("iteration");
        } else {
          next.set("iteration", String(updates.iteration));
        }
      }
      setParams(next, { replace: true });
    },
    [params, setParams],
  );

  const selectCandidate = useCallback(
    (value: number | null) => update({ candidate: value }),
    [update],
  );
  const selectIteration = useCallback(
    (value: number | null) => update({ iteration: value }),
    [update],
  );
  const selectResult = useCallback(
    (value: { candidate?: number | null; iteration?: number | null }) =>
      update(value),
    [update],
  );

  return {
    candidateId,
    iterationIndex,
    selectCandidate,
    selectIteration,
    selectResult,
  };
}

export function resultSearch(params: URLSearchParams): string {
  const value = params.toString();
  return value ? `?${value}` : "";
}
