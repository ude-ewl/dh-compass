import { isValidElement } from "react";
import { Navigate } from "react-router-dom";

import { ComparisonPage } from "../features/comparison/ComparisonPage";
import { ProjectsPage } from "../features/projects/ProjectsPage";
import { createRouteGraph } from "./router";

function childRoute(path: string, redesign = true, legacyRoutes = false) {
  const root = createRouteGraph({
    frontendRedesign: redesign,
    legacyRoutes,
  })[0];
  return root.children?.find((route) => route.path === path);
}

function childElementType(path: string, redesign = true, legacyRoutes = false) {
  const element = childRoute(path, redesign, legacyRoutes)?.element;
  return isValidElement(element) ? element.type : undefined;
}

describe("application route graph", () => {
  it("redirects retired workflow entry points in the default redesign", () => {
    expect(childElementType("projects")).toBe(Navigate);
    expect(childElementType("projects/*")).toBe(Navigate);
    expect(childElementType("compare")).toBe(Navigate);
    expect(childElementType("compare/*")).toBe(Navigate);
  });

  it("exposes the old workflow only when compatibility is enabled", () => {
    expect(childElementType("projects", true, true)).toBe(ProjectsPage);
    expect(childElementType("compare", true, true)).toBe(ComparisonPage);
  });

  it("keeps the existing workflow intact when the redesign is disabled", () => {
    expect(childElementType("projects", false, false)).toBe(ProjectsPage);
    expect(childElementType("compare", false, false)).toBe(ComparisonPage);
  });
});
