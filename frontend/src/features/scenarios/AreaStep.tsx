import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import {
  Alert,
  Button,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  inspectBoundary,
  searchGeocoding,
  updateScenarioArea,
} from "../../api/client";
import type { FeatureCollection, GeoJsonGeometry } from "../../api/results";
import type { BoundaryInspection, StudyArea } from "../../api/workflow";
import { useScenarioAreaQuery } from "../../api/queries";
import { ApiErrorAlert } from "../../components/feedback/ApiErrorAlert";
import {
  FailureState,
  LoadingState,
} from "../../components/feedback/StateViews";
import { ResultMap } from "../results/ResultMap";

interface AreaStepProps {
  scenarioId: string;
  revisionId: string;
  initialBBox: [number, number, number, number];
}

function validBBox(
  values: number[],
): values is [number, number, number, number] {
  return (
    values.length === 4 &&
    values.every((value) => Number.isFinite(value)) &&
    values[0] < values[2] &&
    values[1] < values[3] &&
    values[0] >= -180 &&
    values[2] <= 180 &&
    values[1] >= -90 &&
    values[3] <= 90
  );
}

function bboxFeature(
  bbox: [number, number, number, number],
): FeatureCollection {
  const [west, south, east, north] = bbox;
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [west, south],
              [east, south],
              [east, north],
              [west, north],
              [west, south],
            ],
          ],
        },
        properties: { layer: "execution_bbox" },
      },
    ],
  } as FeatureCollection;
}

function AreaMap({
  area,
  bbox,
  drawing,
  onBoundingBoxChange,
}: {
  area: StudyArea | null;
  bbox: [number, number, number, number];
  drawing: boolean;
  onBoundingBoxChange: (bbox: [number, number, number, number]) => void;
}) {
  useLocale();
  const displayGeometry = area?.display_geometry;
  const displayCollection = displayGeometry
    ? ({
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            geometry: displayGeometry as unknown as GeoJsonGeometry,
            properties: { layer: "imported_boundary" },
          },
        ],
      } as FeatureCollection)
    : null;
  return (
    <Stack spacing={1}>
      <ResultMap
        candidateNetwork={bboxFeature(bbox)}
        editableBoundingBox={bbox}
        bboxDrawingEnabled={drawing}
        lhd={displayCollection}
        onBoundingBoxChange={onBoundingBoxChange}
        showFinalNetwork={false}
        showLhd={Boolean(displayCollection)}
        showPaths={false}
        title={tr("Study area map")}
      />
      <Stack direction="row" spacing={2}>
        <Typography color="primary.main" variant="caption">
          {tr("Blue: execution bbox")}
        </Typography>
        <Typography color="warning.main" variant="caption">
          {tr("Orange: imported/display boundary")}
        </Typography>
      </Stack>
    </Stack>
  );
}

export function AreaStep({
  scenarioId,
  revisionId,
  initialBBox,
}: AreaStepProps) {
  useLocale();
  const queryClient = useQueryClient();
  const area = useScenarioAreaQuery(scenarioId);
  const [values, setValues] = useState<number[]>(initialBBox);
  const [geometry, setGeometry] = useState<Record<string, unknown> | null>(
    null,
  );
  const [source, setSource] = useState<
    "bbox" | "geocoded" | "boundary_upload" | "manual"
  >("bbox");
  const [filename, setFilename] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [boundaryIssue, setBoundaryIssue] = useState<BoundaryInspection | null>(
    null,
  );
  const [drawing, setDrawing] = useState(false);
  const [place, setPlace] = useState("");
  const [placeResults, setPlaceResults] = useState<
    Awaited<ReturnType<typeof searchGeocoding>>["results"]
  >([]);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (area.data && !dirty) {
      setValues(area.data.execution_bbox);
      setGeometry(area.data.display_geometry);
      setSource(area.data.source as typeof source);
      setFilename(area.data.imported_filename);
    }
  }, [area.data, dirty]);

  const bbox = useMemo(
    () => (validBBox(values) ? values : initialBBox),
    [initialBBox, values],
  );
  const areaMutation = useMutation({
    mutationFn: () => {
      if (!validBBox(values)) throw new Error("Enter a valid bounding box.");
      return updateScenarioArea(scenarioId, {
        bbox: values,
        expected_revision_id: revisionId,
        display_geometry: geometry,
        source,
        imported_filename: filename,
      });
    },
    onSuccess: async () => {
      setDirty(false);
      setBoundaryIssue(null);
      await queryClient.invalidateQueries({
        queryKey: ["scenario", scenarioId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["scenario", scenarioId, "config"],
      });
      await queryClient.invalidateQueries({
        queryKey: ["scenario", scenarioId, "area"],
      });
      await queryClient.invalidateQueries({
        queryKey: ["scenario", scenarioId, "datasets"],
      });
    },
  });

  const geocode = useMutation({
    mutationFn: () => searchGeocoding(place.trim()),
    onSuccess: (response) => setPlaceResults(response.results),
  });

  const changeValue = (index: number, raw: string) => {
    const next = [...values];
    next[index] = raw === "" ? Number.NaN : Number(raw);
    setValues(next);
    setSource("manual");
    setDirty(true);
    areaMutation.reset();
  };

  const choosePlace = (result: (typeof placeResults)[number]) => {
    if (!result.bbox || result.bbox.length !== 4) return;
    const next = result.bbox as [number, number, number, number];
    setValues(next);
    setGeometry(result.geometry);
    setSource("geocoded");
    setDirty(true);
    setPlaceResults([]);
  };

  const inspectFile = (file: File | undefined) => {
    if (!file) return;
    setFilename(file.name);
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const document = JSON.parse(String(reader.result)) as Record<
          string,
          unknown
        >;
        void inspectBoundary(document).then((inspection) => {
          setBoundaryIssue(inspection);
          if (!inspection.valid || !inspection.execution_bbox) return;
          setValues(inspection.execution_bbox);
          setGeometry(inspection.display_geometry);
          setSource("boundary_upload");
          setDirty(true);
        });
      } catch {
        setBoundaryIssue({
          valid: false,
          execution_bbox: null,
          display_geometry: null,
          source_crs: null,
          normalized_crs: "EPSG:4326",
          feature_count: 0,
          issues: [
            {
              severity: "error",
              code: "BOUNDARY_JSON_INVALID",
              message: "The selected file is not valid JSON.",
            },
          ],
        });
      }
    };
    reader.readAsText(file);
  };

  if (area.isPending) return <LoadingState label={tr("Loading study area…")} />;
  if (area.isError)
    return (
      <FailureState error={area.error} onRetry={() => void area.refetch()} />
    );

  const currentArea = area.data ?? null;
  return (
    <Stack spacing={2}>
      <Paper component="section" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="h5">{tr("Study area")}</Typography>
          <Typography color="text.secondary">
            {tr(
              "Choose a place, draw or edit the execution rectangle, or import a boundary. The imported geometry is retained separately from the rectangular preprocessing extent.",
            )}
          </Typography>
          <Stack direction={{ md: "row", xs: "column" }} spacing={1}>
            <TextField
              fullWidth
              label={tr("Search for a place")}
              onChange={(event) => setPlace(event.target.value)}
              value={place}
            />
            <Button
              disabled={!place.trim() || geocode.isPending}
              onClick={() => geocode.mutate()}
              variant="outlined"
            >
              {tr(geocode.isPending ? "Searching…" : "Search")}
            </Button>
          </Stack>
          {geocode.isError && <ApiErrorAlert error={geocode.error} />}
          {placeResults.length > 0 && (
            <Stack aria-label={tr("Place search results")} spacing={1}>
              {placeResults.map((result) => (
                <Button
                  key={`${result.display_name}-${result.provider_id ?? "result"}`}
                  onClick={() => choosePlace(result)}
                  sx={{ justifyContent: "flex-start" }}
                  variant="text"
                >
                  {result.display_name}
                </Button>
              ))}
            </Stack>
          )}
          <Button
            aria-pressed={drawing}
            onClick={() => setDrawing((active) => !active)}
            variant={drawing ? "contained" : "text"}
          >
            {tr(
              drawing
                ? "Drawing new box — drag on the map"
                : "Draw a new bounding box",
            )}
          </Button>
          <Typography color="text.secondary" variant="body2">
            {tr(
              "Drag a blue corner handle to resize the current box, or use Draw a new bounding box and drag across the map to replace it.",
            )}
          </Typography>
          {drawing && (
            <Alert severity="info">
              {tr(
                "Drag from one corner of the study area to the opposite corner on the map.",
              )}
            </Alert>
          )}
          <Stack direction={{ sm: "row", xs: "column" }} spacing={1}>
            {[
              ["West", "Longitude"],
              ["South", "Latitude"],
              ["East", "Longitude"],
              ["North", "Latitude"],
            ].map(([label, helper], index) => (
              <TextField
                error={
                  values[index] !== undefined && !Number.isFinite(values[index])
                }
                fullWidth
                helperText={tr(helper)}
                inputProps={{ inputMode: "decimal" }}
                key={label}
                label={tr(label)}
                onChange={(event) => changeValue(index, event.target.value)}
                type="number"
                value={Number.isFinite(values[index]) ? values[index] : ""}
              />
            ))}
          </Stack>
          {!validBBox(values) && (
            <Alert severity="error">
              {tr(
                "Enter west < east and south < north using WGS84 coordinates.",
              )}
            </Alert>
          )}
          <Button component="label" variant="outlined">
            {tr(filename ? `Boundary: ${filename}` : "Import GeoJSON boundary")}
            <input
              accept=".geojson,.json,application/geo+json,application/json"
              hidden
              onChange={(event) => inspectFile(event.target.files?.[0])}
              ref={inputRef}
              type="file"
            />
          </Button>
          {boundaryIssue?.issues.map((issue) => (
            <Alert
              key={`${issue.code}-${issue.message}`}
              severity={issue.severity === "error" ? "error" : "warning"}
            >
              {tr(issue.message)}
            </Alert>
          ))}
          {areaMutation.isError && <ApiErrorAlert error={areaMutation.error} />}
          {areaMutation.isSuccess && !dirty && (
            <Alert severity="success">{tr("Study area saved.")}</Alert>
          )}
          <Button
            disabled={!validBBox(values) || areaMutation.isPending || !dirty}
            onClick={() => areaMutation.mutate()}
            variant="contained"
          >
            {tr(
              areaMutation.isPending
                ? "Saving area…"
                : "Save and validate area",
            )}
          </Button>
        </Stack>
      </Paper>
      <AreaMap
        area={currentArea}
        bbox={bbox}
        drawing={drawing}
        onBoundingBoxChange={(next) => {
          setValues(next);
          setSource("manual");
          setDirty(true);
          setDrawing(false);
          areaMutation.reset();
        }}
      />
    </Stack>
  );
}
