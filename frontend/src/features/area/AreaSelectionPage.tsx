import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Alert,
  Box,
  Button,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { searchGeocoding, startCalculation } from "../../api/client";
import type { CalculationAccepted } from "../../api/calculations";
import { useCalculationContractQuery } from "../../api/queries";
import { ApiErrorAlert } from "../../components/feedback/ApiErrorAlert";
import { BoundingBoxMap } from "./BoundingBoxMap";
import { BoundingBoxToolbar } from "./BoundingBoxToolbar";
import {
  DEFAULT_BBOX_LIMITS,
  formatCoordinate,
  validateBBox,
  type BBox,
  type BBoxLimits,
} from "./bbox";
import { ExactExtentPanel } from "./ExactExtentPanel";

type CoordinateValues = [string, string, string, string];
const EMPTY_COORDINATES: CoordinateValues = ["", "", "", ""];
type SearchResult = Awaited<
  ReturnType<typeof searchGeocoding>
>["results"][number];

interface AreaSelectionPageProps {
  /** Dependency injection keeps the page deterministic in component tests. */
  submitCalculation?: (
    bbox: BBox,
    idempotencyKey: string,
  ) => Promise<CalculationAccepted>;
}

function limitsFromContract(
  contract:
    | {
        bbox: {
          coverage_bbox: BBox;
          min_area_km2: number;
          max_area_km2: number;
        };
      }
    | undefined,
): BBoxLimits {
  if (!contract) return DEFAULT_BBOX_LIMITS;
  return {
    coverageBBox: contract.bbox.coverage_bbox,
    minAreaKm2: contract.bbox.min_area_km2,
    maxAreaKm2: contract.bbox.max_area_km2,
  };
}

function bboxFromValues(values: CoordinateValues): BBox | null {
  const numbers = values.map((value) => Number(value));
  return validateBBox(numbers).bbox &&
    numbers.every((value) => Number.isFinite(value)) &&
    numbers[0] < numbers[2] &&
    numbers[1] < numbers[3]
    ? (numbers as BBox)
    : null;
}

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `hgp-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function resultBBox(result: SearchResult): BBox | null {
  if (!result.bbox || result.bbox.length !== 4) return null;
  const values = result.bbox.map(Number);
  if (!values.every((value) => Number.isFinite(value))) return null;
  const [west, south, east, north] = values;
  if (west >= east || south >= north) return null;
  return [west, south, east, north];
}

/**
 * Read a rectangle handed back by a failed or cancelled run.
 *
 * The run record is immutable, so a retry starts a new calculation. Carrying
 * the rectangle keeps the active study area from being lost on the way.
 */
function bboxFromParam(value: string | null, limits: BBoxLimits): BBox | null {
  if (!value) return null;
  const parts = value.split(",").map((item) => Number(item.trim()));
  const validation = validateBBox(parts, limits);
  return validation.issues.length === 0 ? (validation.bbox as BBox) : null;
}

export function AreaSelectionPage({
  submitCalculation = startCalculation,
}: AreaSelectionPageProps) {
  useLocale();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const contract = useCalculationContractQuery();
  const limits = limitsFromContract(contract.data);
  const [coordinates, setCoordinates] =
    useState<CoordinateValues>(EMPTY_COORDINATES);
  const [bbox, setBBox] = useState<BBox | null>(null);
  const [draftBBox, setDraftBBox] = useState<BBox | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [showValidation, setShowValidation] = useState(false);
  const [place, setPlace] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchSelection, setSearchSelection] = useState<SearchResult | null>(
    null,
  );
  const [focusBBox, setFocusBBox] = useState<BBox | null>(null);
  const [fitRequest, setFitRequest] = useState(0);
  const idempotencyKeyRef = useRef<string | null>(null);
  const submittedBBoxRef = useRef<string | null>(null);
  const submissionInFlightRef = useRef(false);

  const validation = validateBBox(
    coordinates.map((value) => Number(value)),
    limits,
  );
  const visibleIssues =
    showValidation || coordinates.some(Boolean) ? validation.issues : [];
  const draftValidation = draftBBox
    ? validateBBox(draftBBox, limits)
    : validation;
  const displayedCoordinates = draftBBox
    ? (draftBBox.map(formatCoordinate) as CoordinateValues)
    : coordinates;
  const displayedIssues = draftBBox ? draftValidation.issues : visibleIssues;

  const search = useMutation({
    mutationFn: () => searchGeocoding(place.trim()),
    onSuccess: (response) => {
      setSearchResults(response.results);
      setSearchSelection(null);
      setFocusBBox(null);
    },
  });

  const calculation = useMutation({
    mutationFn: async () => {
      if (!bbox || validation.issues.length > 0) {
        throw new Error(
          "Choose a valid study area before starting the calculation.",
        );
      }
      const keyForBBox = JSON.stringify(bbox);
      if (submittedBBoxRef.current !== keyForBBox) {
        idempotencyKeyRef.current = newIdempotencyKey();
        submittedBBoxRef.current = keyForBBox;
      }
      return submitCalculation(
        bbox,
        idempotencyKeyRef.current ?? newIdempotencyKey(),
      );
    },
    onSuccess: (response) => {
      navigate(`/runs/${encodeURIComponent(response.run_id)}`);
    },
    onSettled: () => {
      submissionInFlightRef.current = false;
    },
  });

  const updateCoordinate = (index: number, value: string) => {
    const next = [...coordinates] as CoordinateValues;
    next[index] = value;
    setCoordinates(next);
    setShowValidation(true);
    if (searchSelection) setSearchSelection(null);
    const nextBBox = bboxFromValues(next);
    // Do not leave a previously valid rectangle visible for a different,
    // currently invalid exact extent. The map returns when all four values
    // again form an ordered bbox.
    setBBox(nextBBox);
    setDraftBBox(null);
    setFocusBBox(null);
    calculation.reset();
  };

  const commitBBox = (next: BBox) => {
    setCoordinates(next.map(formatCoordinate) as CoordinateValues);
    setBBox(next);
    setDraftBBox(null);
    setShowValidation(true);
    setSearchSelection(null);
    setFocusBBox(null);
    calculation.reset();
  };

  // A failed or cancelled run hands its rectangle back here so the user starts
  // the next calculation from the same area instead of drawing it again. The
  // server owns the bbox limits, so the parameter waits for the contract
  // instead of being judged against the client's fallback defaults, and it is
  // consumed once: the parameter is removed from the address either way.
  const handedBackBBox = searchParams.get("bbox");
  const contractData = contract.data;
  const contractUnavailable = contract.isError;
  useEffect(() => {
    if (!handedBackBBox) return;
    if (!contractData && !contractUnavailable) return;
    setSearchParams(
      (current) => {
        const remaining = new URLSearchParams(current);
        remaining.delete("bbox");
        remaining.delete("retry");
        return remaining;
      },
      { replace: true },
    );
    const next = bboxFromParam(
      handedBackBBox,
      limitsFromContract(contractData),
    );
    if (!next) return;
    commitBBox(next);
    setFocusBBox(next);
    // `commitBBox` and `setFocusBBox` are recreated each render; the rectangle
    // must be applied exactly once per handed-back parameter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contractData, contractUnavailable, handedBackBBox, setSearchParams]);

  const selectSearchResult = (result: SearchResult) => {
    const next = resultBBox(result);
    setSearchSelection(result);
    setSearchResults([]);
    if (next) setFocusBBox(next);
  };

  const useSearchExtent = () => {
    const next = searchSelection ? resultBBox(searchSelection) : null;
    if (!next) return;
    commitBBox(next);
    setFocusBBox(next);
  };

  const startDrawing = () => {
    setDrawing((value) => !value);
  };

  return (
    <Box
      className="area-selection-page viewer-area"
      sx={{ height: "100%", minHeight: 0, position: "relative", width: "100%" }}
    >
      <Typography
        component="h1"
        sx={{
          clip: "rect(0 0 0 0)",
          clipPath: "inset(50%)",
          height: 1,
          overflow: "hidden",
          position: "absolute",
          whiteSpace: "nowrap",
          width: 1,
        }}
      >
        {tr("Select a study area")}
      </Typography>
      <BoundingBoxMap
        bbox={bbox}
        drawingEnabled={drawing}
        fitRequest={fitRequest}
        focusBBox={focusBBox}
        limits={limits}
        onChange={commitBBox}
        onDraftChange={setDraftBBox}
        onDrawingChange={setDrawing}
        title={tr("Study area map")}
      />

      <aside
        className="viewer-sidebar area-sidebar"
        aria-label={tr("Study area controls")}
      >
        <h2>{tr("Study area")}</h2>
        <p className="viewer-muted">
          {tr(
            "Choose an area on the map, then start the calculation. Watch the grid grow here as each subgraph is evaluated.",
          )}
        </p>
        <Paper
          component="section"
          elevation={2}
          sx={{ borderRadius: 0, boxShadow: "none" }}
        >
          <Box
            component="form"
            onSubmit={(event) => {
              event.preventDefault();
              if (place.trim()) search.mutate();
            }}
            sx={{ p: 1.5 }}
          >
            <Stack spacing={1}>
              <Typography component="h2" variant="subtitle1">
                {tr("Find a place")}
              </Typography>
              <Stack direction="row" spacing={1}>
                <TextField
                  fullWidth
                  label={tr("Search for a place")}
                  onChange={(event) => setPlace(event.target.value)}
                  placeholder={tr("Town, municipality, or address")}
                  size="small"
                  value={place}
                />
                <Button
                  disabled={!place.trim() || search.isPending}
                  type="submit"
                  variant="outlined"
                >
                  {tr(search.isPending ? "Searching…" : "Search")}
                </Button>
              </Stack>
              {search.isError && (
                <ApiErrorAlert
                  error={search.error}
                  onRetry={() => search.mutate()}
                  retryLabel={tr("Retry search")}
                />
              )}
              {search.data?.warning && (
                <Alert severity="warning">{tr(search.data.warning)}</Alert>
              )}
              {searchResults.length > 0 && (
                <Stack
                  aria-label={tr("Place search results")}
                  role="listbox"
                  spacing={0.25}
                >
                  {searchResults.map((result) => (
                    <Button
                      key={`${result.display_name}-${result.provider_id ?? "result"}`}
                      onClick={() => selectSearchResult(result)}
                      role="option"
                      sx={{ justifyContent: "flex-start", textAlign: "left" }}
                      variant="text"
                    >
                      {result.display_name}
                    </Button>
                  ))}
                </Stack>
              )}
              {searchSelection && (
                <Alert
                  action={
                    resultBBox(searchSelection) ? (
                      <Button
                        color="inherit"
                        onClick={useSearchExtent}
                        size="small"
                      >
                        {tr("Use extent")}
                      </Button>
                    ) : undefined
                  }
                  severity="info"
                >
                  {tr("Viewport moved to ")}
                  {searchSelection.display_name}
                  {tr(". The selected area was not changed.")}
                </Alert>
              )}
            </Stack>
          </Box>
        </Paper>

        <Paper
          component="section"
          elevation={3}
          sx={{ borderRadius: 0, boxShadow: "none" }}
        >
          <Stack spacing={1} sx={{ p: { sm: 1.5, xs: 1 } }}>
            <ExactExtentPanel
              issues={displayedIssues}
              onChange={updateCoordinate}
              values={displayedCoordinates}
            />
            <BoundingBoxToolbar
              compact
              areaKm2={draftValidation.areaKm2}
              bbox={bbox}
              drawing={drawing}
              onDraw={startDrawing}
              onFit={() => {
                setFocusBBox(null);
                setFitRequest((value) => value + 1);
              }}
              onStart={() => {
                if (submissionInFlightRef.current) return;
                submissionInFlightRef.current = true;
                setShowValidation(true);
                calculation.mutate();
              }}
              submitting={calculation.isPending}
              validationIssues={displayedIssues}
            />
            {contract.isError && (
              <Alert
                action={
                  <Button
                    color="inherit"
                    onClick={() => void contract.refetch()}
                    size="small"
                  >
                    {tr("Retry")}
                  </Button>
                }
                severity="warning"
              >
                {tr(
                  "Bbox limits could not be loaded. The server will validate the selected area before accepting a calculation.",
                )}
              </Alert>
            )}
            {calculation.isError && (
              <ApiErrorAlert
                error={calculation.error}
                onRetry={() => calculation.mutate()}
              />
            )}
            {calculation.isSuccess && (
              <Alert severity="success">
                {tr("Calculation accepted. Restoring the run…")}
              </Alert>
            )}
          </Stack>
        </Paper>
      </aside>
    </Box>
  );
}

export type { AreaSelectionPageProps };
