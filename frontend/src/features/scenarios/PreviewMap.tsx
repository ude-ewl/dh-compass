import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Stack, Typography } from "@mui/material";

import type { FeatureCollection } from "../../api/results";
import { ResultMap } from "../results/ResultMap";

interface PreviewMapProps {
  candidateAreas?: FeatureCollection | null;
  lhd?: FeatureCollection | null;
  buildings?: FeatureCollection | null;
  screenedOut?: FeatureCollection | null;
  selectedCandidateId?: number | null;
  onSelectCandidate?: (id: number) => void;
}

function PreviewLayerLegend() {
  useLocale();
  return (
    <Stack
      aria-label={tr("Preview map legend")}
      direction="row"
      flexWrap="wrap"
      gap={1}
    >
      <Typography color="success.main" variant="caption">
        {tr("● Candidate area")}
      </Typography>
      <Typography color="warning.main" variant="caption">
        {tr("━ LHD edge")}
      </Typography>
      <Typography color="text.secondary" variant="caption">
        {tr("┄ Screened out")}
      </Typography>
      <Typography color="primary.main" variant="caption">
        {tr("● Building")}
      </Typography>
    </Stack>
  );
}

export function PreviewMap({
  candidateAreas,
  lhd,
  buildings,
  screenedOut,
  selectedCandidateId = null,
  onSelectCandidate,
}: PreviewMapProps) {
  useLocale();
  return (
    <Stack aria-label={tr("Candidate preview map")} spacing={1}>
      <ResultMap
        buildingLocations={buildings}
        candidateNetwork={candidateAreas}
        connectionPaths={null}
        lhd={lhd}
        onSelectCandidate={onSelectCandidate}
        selectedCandidateId={selectedCandidateId}
        showCandidates
        showLhd
        showPaths
        title={tr("Candidate preview map")}
        screenedOut={screenedOut}
      />
      <PreviewLayerLegend />
    </Stack>
  );
}
