import { describe, expect, it } from "vitest";

import {
  redesignedRunLocation,
  redesignedRunMonitorPath,
  redesignedRunPath,
} from "./routeMigration";

describe("redesigned run route migration", () => {
  it("maps the monitor and overview bookmarks to the run workspace", () => {
    expect(redesignedRunMonitorPath("demo/run-1")).toBe("/runs/demo%2Frun-1");
    expect(redesignedRunPath("run-1", "overview")).toBe("/runs/run-1");
  });

  it("keeps network and downloads entry points available", () => {
    expect(redesignedRunPath("run-1", "network")).toBe("/runs/run-1/network");
    expect(redesignedRunPath("run-1", "downloads")).toBe("/runs/run-1/files");
  });

  it("preserves query and fragment state from old result bookmarks", () => {
    expect(
      redesignedRunLocation("run-1", "network", "?candidate=7", "#table"),
    ).toBe("/runs/run-1/network?candidate=7#table");
  });
});
