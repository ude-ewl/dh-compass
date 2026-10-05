export interface FrontendFeatureFlags {
  /** Enable the constrained area → calculation → result route graph. */
  frontendRedesign: boolean;
}

function asBoolean(value: unknown, fallback = false): boolean {
  if (typeof value !== "string") return fallback;
  switch (value.trim().toLowerCase()) {
    case "1":
    case "true":
    case "yes":
    case "on":
      return true;
    case "0":
    case "false":
    case "no":
    case "off":
      return false;
    default:
      return fallback;
  }
}

export function readFeatureFlags(
  environment: Record<string, unknown> = import.meta.env,
): FrontendFeatureFlags {
  return {
    frontendRedesign: asBoolean(
      environment.VITE_DH_COMPASS_FRONTEND_REDESIGN ??
        environment.VITE_FRONTEND_REDESIGN,
      true,
    ),
  };
}

/**
 * Flags are evaluated once at module load, matching Vite's build-time env
 * semantics. The constrained route graph is the release default; an explicit
 * false value is retained only for a temporary rollback deployment.
 */
export const featureFlags = readFeatureFlags();

/**
 * Keep the old project/scenario workflow available only when an installation
 * explicitly needs it during the redesign rollout. The flag is intentionally
 * separate from `frontendRedesign`: enabling the redesign must not silently
 * leave a second set of user decisions in the default route graph.
 *
 * `VITE_DH_COMPASS_FRONTEND_LEGACY_ROUTES` (or its shorter alias) can be
 * enabled for a rollback window. Legacy routes are always available while the
 * redesign flag itself is off.
 */
export function readLegacyRouteCompatibility(
  environment: Record<string, unknown> = import.meta.env,
): boolean {
  return asBoolean(
    environment.VITE_DH_COMPASS_FRONTEND_LEGACY_ROUTES ??
      environment.VITE_FRONTEND_LEGACY_ROUTES,
  );
}

export const legacyRouteCompatibility = readLegacyRouteCompatibility();
