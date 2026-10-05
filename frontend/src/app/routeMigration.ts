export type LegacyResultTab =
  | "overview"
  | "network"
  | "decisions"
  | "supply"
  | "costs"
  | "decentral"
  | "downloads";

/**
 * Map bookmarks from the seven-tab result shell to the constrained route
 * graph. This is pure so redirects can be characterized without rendering a
 * map or making an API request.
 */
export function redesignedRunPath(
  runId: string,
  tab: LegacyResultTab = "overview",
): string {
  const encoded = encodeURIComponent(runId);
  if (tab === "network" || tab === "decisions" || tab === "decentral") {
    return `/runs/${encoded}/network`;
  }
  if (tab === "downloads") return `/runs/${encoded}/files`;
  return `/runs/${encoded}`;
}

export function redesignedRunMonitorPath(runId: string): string {
  return redesignedRunPath(runId);
}

/** Preserve query and fragment state when replacing a legacy bookmark. */
export function redesignedRunLocation(
  runId: string,
  tab: LegacyResultTab = "overview",
  search = "",
  hash = "",
): string {
  return `${redesignedRunPath(runId, tab)}${search}${hash}`;
}
