import { readFeatureFlags, readLegacyRouteCompatibility } from "./featureFlags";
import { redesignedRunPath } from "./routeMigration";

describe("frontend redesign rollout contract", () => {
  it("uses the constrained route graph by default", () => {
    expect(readFeatureFlags({})).toEqual({ frontendRedesign: true });
  });

  it("accepts explicit Vite rollback values", () => {
    expect(
      readFeatureFlags({ VITE_DH_COMPASS_FRONTEND_REDESIGN: "false" }),
    ).toEqual({ frontendRedesign: false });
    expect(readFeatureFlags({ VITE_FRONTEND_REDESIGN: "0" })).toEqual({
      frontendRedesign: false,
    });
  });

  it("keeps legacy workflow routes opt-in during the redesign", () => {
    expect(readLegacyRouteCompatibility({})).toBe(false);
    expect(
      readLegacyRouteCompatibility({
        VITE_DH_COMPASS_FRONTEND_LEGACY_ROUTES: "true",
      }),
    ).toBe(true);
    expect(
      readLegacyRouteCompatibility({ VITE_FRONTEND_LEGACY_ROUTES: "1" }),
    ).toBe(true);
  });

  it("maps legacy result bookmarks to the constrained route graph", () => {
    expect(redesignedRunPath("demo/run-1", "overview")).toBe(
      "/runs/demo%2Frun-1",
    );
    expect(redesignedRunPath("run-1", "decisions")).toBe("/runs/run-1/network");
    expect(redesignedRunPath("run-1", "downloads")).toBe("/runs/run-1/files");
  });
});
