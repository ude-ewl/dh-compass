import { useLocale } from "../i18n/locale";
import { Navigate, useLocation, useParams } from "react-router-dom";

import { redesignedRunLocation } from "./routeMigration";

export function LegacyRunRedirect() {
  useLocale();
  // useParams gives us the decoded opaque identifier, so a legacy output ID
  // containing a slash is encoded exactly once in its replacement URL.
  const { runId = "" } = useParams();
  const location = useLocation();
  return (
    <Navigate
      replace
      to={redesignedRunLocation(
        runId,
        "overview",
        location.search,
        location.hash,
      )}
    />
  );
}

export function LegacyResultRedirect() {
  useLocale();
  const { runId = "", tab } = useParams();
  const location = useLocation();
  const resultTab = tab as Parameters<typeof redesignedRunLocation>[1];
  return (
    <Navigate
      replace
      to={redesignedRunLocation(
        runId,
        resultTab,
        location.search,
        location.hash,
      )}
    />
  );
}
