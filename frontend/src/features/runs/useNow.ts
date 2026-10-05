import { useEffect, useState } from "react";

/**
 * A ticking clock for elapsed-time displays.
 *
 * The value is only refreshed while something is running, so a finished run
 * stops re-rendering and its elapsed time freezes at the recorded finish time.
 */
export function useNow(active: boolean, intervalMs = 1_000): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!active) return undefined;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [active, intervalMs]);

  return now;
}
