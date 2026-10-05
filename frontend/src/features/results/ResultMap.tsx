import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { formatNumber } from "./format";
import { Alert, Box, Button, Paper, Stack, Typography } from "@mui/material";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type { FeatureCollection, GeoJsonFeature } from "../../api/results";
import { MapErrorOverlay } from "../../components/map/MapErrorOverlay";

interface ResultMapProps {
  /** Fill the classic viewer's map pane without a second toolbar. */
  viewerMode?: boolean;
  finalNetwork?: FeatureCollection | null;
  candidateNetwork?: FeatureCollection | null;
  lhd?: FeatureCollection | null;
  connectionPaths?: FeatureCollection | null;
  buildingLocations?: FeatureCollection | null;
  screenedOut?: FeatureCollection | null;
  selectedCandidateId?: number | null;
  onSelectCandidate?: (candidateId: number) => void;
  showCandidates?: boolean;
  showFinalNetwork?: boolean;
  showLhd?: boolean;
  showPaths?: boolean;
  showBuildings?: boolean;
  showScreenedOut?: boolean;
  /** Increment this value from an external layer toolbar to fit the extent. */
  fitRequest?: number;
  /** The WGS84 rectangle shown while configuring a study area. */
  editableBoundingBox?: [number, number, number, number] | null;
  /** Enables drag-to-draw interaction for the study-area rectangle. */
  bboxDrawingEnabled?: boolean;
  onBoundingBoxChange?: (bbox: [number, number, number, number]) => void;
  title?: string;
}

interface CoordinateExtent {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

type LayerVisibility = {
  candidates: boolean;
  finalNetwork: boolean;
  lhd: boolean;
  paths: boolean;
  buildings: boolean;
  screenedOut: boolean;
};

/**
 * Defensive client limit for interactive layers. The API may serve a large
 * GeoJSON artifact, but a browser must not try to build thousands of DOM and
 * WebGL objects after a partial or stale response. The complete decision table
 * remains available beside the map.
 */
const MAX_MAP_FEATURES = 10_000;
const MAX_FALLBACK_FEATURES = MAX_MAP_FEATURES;

const emptyCollection: FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

const layerIds = {
  network: "result-network",
  candidates: "result-candidates",
  lhd: "result-lhd",
  paths: "result-paths",
  buildings: "result-buildings",
  screenedOut: "result-screened-out",
  boundingBox: "result-study-area-bbox",
  boundingBoxHandles: "result-study-area-bbox-handles",
} as const;

interface PreparedFeatureCollection {
  collection: FeatureCollection;
  droppedFeatures: number;
  malformedCollection: boolean;
}

function hasFiniteCoordinates(value: unknown, depth = 0): boolean {
  // API JSON cannot be cyclic, but capping nesting still prevents a malformed
  // response from exhausting the browser stack before the map can recover.
  if (depth > 16 || !Array.isArray(value) || value.length === 0) return false;
  if (
    value.length >= 2 &&
    typeof value[0] === "number" &&
    Number.isFinite(value[0]) &&
    typeof value[1] === "number" &&
    Number.isFinite(value[1])
  ) {
    return value.every(
      (coordinate) =>
        typeof coordinate === "number" && Number.isFinite(coordinate),
    );
  }
  return value.every((item) => hasFiniteCoordinates(item, depth + 1));
}

function isSafeFeature(value: unknown): value is GeoJsonFeature {
  if (!value || typeof value !== "object") return false;
  const feature = value as Record<string, unknown>;
  if (feature.type !== "Feature") return false;
  if (feature.geometry === null) return true;
  if (!feature.geometry || typeof feature.geometry !== "object") return false;
  const geometry = feature.geometry as Record<string, unknown>;
  const type = geometry.type;
  if (type === "GeometryCollection") {
    return (
      Array.isArray(geometry.geometries) &&
      geometry.geometries.every((item) =>
        isSafeFeature({ type: "Feature", geometry: item }),
      )
    );
  }
  return (
    typeof type === "string" &&
    [
      "Point",
      "MultiPoint",
      "LineString",
      "MultiLineString",
      "Polygon",
      "MultiPolygon",
    ].includes(type) &&
    hasFiniteCoordinates(geometry.coordinates)
  );
}

/** Normalize untrusted GeoJSON before giving it to MapLibre or the fallback. */
function prepareFeatureCollection(
  value: FeatureCollection | null | undefined,
): PreparedFeatureCollection {
  if (
    !value ||
    value.type !== "FeatureCollection" ||
    !Array.isArray(value.features)
  ) {
    return {
      collection: emptyCollection,
      droppedFeatures: 0,
      malformedCollection: value !== null && value !== undefined,
    };
  }
  const features = value.features.filter(isSafeFeature);
  return {
    collection: { ...value, features },
    droppedFeatures: value.features.length - features.length,
    malformedCollection: false,
  };
}

/** Keep a previously normalized collection bounded without mutating it. */
function limitFeatureCollection(
  collection: FeatureCollection,
  limit = MAX_MAP_FEATURES,
): FeatureCollection {
  if (collection.features.length <= limit) return collection;
  return { ...collection, features: collection.features.slice(0, limit) };
}

function boundingBoxCollection(
  bbox: [number, number, number, number] | null | undefined,
): FeatureCollection {
  if (!bbox) return emptyCollection;
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
        properties: { layer: "study_area_bbox" },
      },
    ],
  } as FeatureCollection;
}

function boundingBoxHandleCollection(
  bbox: [number, number, number, number] | null | undefined,
): FeatureCollection {
  if (!bbox) return emptyCollection;
  const [west, south, east, north] = bbox;
  const corners: Array<[string, [number, number]]> = [
    ["southwest", [west, south]],
    ["northwest", [west, north]],
    ["northeast", [east, north]],
    ["southeast", [east, south]],
  ];
  return {
    type: "FeatureCollection",
    features: corners.map(([corner, coordinates]) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates },
      properties: { corner },
    })),
  } as FeatureCollection;
}

function normalizedBoundingBox(
  start: [number, number],
  end: [number, number],
): [number, number, number, number] {
  return [
    Math.min(start[0], end[0]),
    Math.min(start[1], end[1]),
    Math.max(start[0], end[0]),
    Math.max(start[1], end[1]),
  ];
}

function collectCoordinates(value: unknown, output: [number, number][]): void {
  if (!Array.isArray(value)) return;
  if (
    value.length >= 2 &&
    typeof value[0] === "number" &&
    typeof value[1] === "number"
  ) {
    output.push([value[0], value[1]]);
    return;
  }
  value.forEach((item) => collectCoordinates(item, output));
}

function extentFor(collections: FeatureCollection[]): CoordinateExtent | null {
  const coordinates: [number, number][] = [];
  collections.forEach((collection) =>
    collection.features.forEach((feature) =>
      collectCoordinates(feature.geometry?.coordinates, coordinates),
    ),
  );
  if (!coordinates.length) return null;
  const xs = coordinates.map(([x]) => x);
  const ys = coordinates.map(([, y]) => y);
  const xPadding = Math.max((Math.max(...xs) - Math.min(...xs)) * 0.08, 0.001);
  const yPadding = Math.max((Math.max(...ys) - Math.min(...ys)) * 0.08, 0.001);
  return {
    minX: Math.min(...xs) - xPadding,
    maxX: Math.max(...xs) + xPadding,
    minY: Math.min(...ys) - yPadding,
    maxY: Math.max(...ys) + yPadding,
  };
}

function lineParts(feature: GeoJsonFeature): number[][][] {
  const geometry = feature.geometry;
  if (!geometry || !Array.isArray(geometry.coordinates)) return [];
  if (geometry.type === "LineString")
    return [geometry.coordinates as number[][]];
  if (geometry.type === "MultiLineString" || geometry.type === "Polygon") {
    return geometry.coordinates as number[][][];
  }
  return [];
}

function candidateId(feature: GeoJsonFeature): number | null {
  const value = feature.properties?.candidate_id;
  return typeof value === "number" ? value : null;
}

function svgPoints(coordinates: number[][], extent: CoordinateExtent): string {
  return coordinates
    .filter(
      (coordinate) =>
        typeof coordinate[0] === "number" && typeof coordinate[1] === "number",
    )
    .map(([x, y]) => {
      const px = ((x - extent.minX) / (extent.maxX - extent.minX)) * 100;
      const py = 100 - ((y - extent.minY) / (extent.maxY - extent.minY)) * 100;
      return `${px},${py}`;
    })
    .join(" ");
}

function resizeBoundingBox(
  bbox: [number, number, number, number],
  corner: string,
  point: [number, number],
): [number, number, number, number] {
  const [west, south, east, north] = bbox;
  const [longitude, latitude] = point;
  if (corner === "southwest")
    return normalizedBoundingBox([longitude, latitude], [east, north]);
  if (corner === "northwest")
    return normalizedBoundingBox([longitude, south], [east, latitude]);
  if (corner === "northeast")
    return normalizedBoundingBox([west, south], [longitude, latitude]);
  return normalizedBoundingBox([west, latitude], [longitude, south]);
}

function fitMap(
  map: MapLibreMap | null,
  extent: CoordinateExtent | null,
): void {
  if (!map || !extent) return;
  map.fitBounds(
    [
      [extent.minX, extent.minY],
      [extent.maxX, extent.maxY],
    ],
    { padding: 24, duration: 0 },
  );
}

function FallbackMap({
  collections,
  extent,
  selectedCandidateId,
  onSelectCandidate,
  visibility,
}: {
  collections: FeatureCollection[];
  extent: CoordinateExtent | null;
  selectedCandidateId: number | null;
  onSelectCandidate?: (candidateId: number) => void;
  visibility: LayerVisibility;
}) {
  useLocale();
  if (!extent) {
    return (
      <Stack
        alignItems="center"
        justifyContent="center"
        sx={{ height: "100%" }}
      >
        <Typography color="text.secondary">
          {tr("No spatial layer is available.")}
        </Typography>
      </Stack>
    );
  }

  const [network, candidates, lhd, paths, buildings, screenedOut] = collections;
  const renderCollection = (
    collection: FeatureCollection,
    color: string,
    width: number,
    opacity: number,
    highlight = false,
  ) =>
    collection.features
      .slice(0, MAX_FALLBACK_FEATURES)
      .flatMap((feature, featureIndex) => {
        const id = candidateId(feature);
        const selected = highlight && id !== null && id === selectedCandidateId;
        return lineParts(feature).map((part, partIndex) => {
          const points = svgPoints(part, extent);
          if (!points) return null;
          return (
            <polyline
              className="result-map-feature"
              fill="none"
              key={`${featureIndex}-${partIndex}`}
              points={points}
              stroke={selected ? "#ffd600" : color}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeOpacity={selected ? 1 : opacity}
              strokeWidth={selected ? width + 1.5 : width}
              vectorEffect="non-scaling-stroke"
            />
          );
        });
      });

  // A multipart candidate is one selectable planning object, not one
  // keyboard stop per geometry segment. The table below remains the complete
  // accessible alternative for dense or overlapping layers.
  const candidateGroups = new Map<
    number,
    { color: string; features: GeoJsonFeature[] }
  >();
  candidates.features.slice(0, MAX_FALLBACK_FEATURES).forEach((feature) => {
    const id = candidateId(feature);
    if (id === null) return;
    const decision = feature.properties?.decision;
    const color =
      decision === "connected"
        ? "#00c853"
        : decision === "current"
          ? "#ffd600"
          : decision === "rejected"
            ? "#ff1744"
            : "#64748b";
    const group = candidateGroups.get(id) ?? { color, features: [] };
    group.features.push(feature);
    candidateGroups.set(id, group);
  });

  return (
    <svg
      aria-label={tr("Heat network result map")}
      height="100%"
      role="img"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      width="100%"
    >
      <rect fill="#1a1a2e" height="100" width="100" />
      {tr(visibility.lhd && renderCollection(lhd, "#d94801", 1.4, 0.55))}
      {visibility.candidates &&
        [...candidateGroups.entries()].map(([id, group]) => (
          <g
            aria-disabled={onSelectCandidate ? undefined : true}
            aria-label={tr(`Candidate ${id}`)}
            className="result-map-feature"
            key={`candidate-${id}`}
            onClick={
              onSelectCandidate ? () => onSelectCandidate(id) : undefined
            }
            onKeyDown={
              onSelectCandidate
                ? (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelectCandidate(id);
                    }
                  }
                : undefined
            }
            role="button"
            tabIndex={0}
          >
            {tr(
              renderCollection(
                { type: "FeatureCollection", features: group.features },
                group.color,
                1.8,
                0.75,
                true,
              ),
            )}
          </g>
        ))}
      {tr(
        visibility.finalNetwork &&
          renderCollection(network, "#17324d", 2.5, 0.95),
      )}
      {tr(visibility.paths && renderCollection(paths, "#00e676", 2, 0.85))}
      {tr(
        visibility.screenedOut &&
          renderCollection(screenedOut, "#94a3b8", 1, 0.7),
      )}
      {visibility.buildings &&
        buildings.features
          .slice(0, MAX_FALLBACK_FEATURES)
          .flatMap((feature, featureIndex) => {
            const coordinates: [number, number][] = [];
            collectCoordinates(feature.geometry?.coordinates, coordinates);
            return coordinates.map(([x, y], pointIndex) => (
              <circle
                aria-label={tr("Building")}
                cx={((x - extent.minX) / (extent.maxX - extent.minX)) * 100}
                cy={
                  100 - ((y - extent.minY) / (extent.maxY - extent.minY)) * 100
                }
                fill="#1d557d"
                key={`building-${featureIndex}-${pointIndex}`}
                r="0.9"
              />
            ));
          })}
    </svg>
  );
}

function sourceData(collection: FeatureCollection): unknown {
  return collection as unknown;
}

function updateMap(
  map: MapLibreMap,
  collections: FeatureCollection[],
  visibility: LayerVisibility,
  selectedCandidateId: number | null,
): void {
  const updates = [
    [layerIds.network, collections[0]],
    [layerIds.candidates, collections[1]],
    [layerIds.lhd, collections[2]],
    [layerIds.paths, collections[3]],
    [layerIds.buildings, collections[4]],
    [layerIds.screenedOut, collections[5]],
  ] as const;
  updates.forEach(([id, data]) => {
    const source = map.getSource(id);
    if (source && "setData" in source && typeof source.setData === "function") {
      (source.setData as (value: unknown) => void)(sourceData(data));
    }
  });

  const layerVisibility: Array<[string, boolean]> = [
    ["candidate-lines", visibility.candidates],
    ["selected-candidate-line", visibility.candidates],
    ["network-lines", visibility.finalNetwork],
    ["lhd-lines", visibility.lhd],
    ["path-lines", visibility.paths],
    ["building-polygons", visibility.buildings],
    ["building-points", visibility.buildings],
    ["screened-out-lines", visibility.screenedOut],
  ];
  layerVisibility.forEach(([id, visible]) => {
    if (map.getLayer(id)) {
      map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
    }
  });
  if (map.getLayer("selected-candidate-line")) {
    map.setFilter("selected-candidate-line", [
      "==",
      ["get", "candidate_id"],
      selectedCandidateId ?? -999999,
    ]);
  }
  // Fitting belongs to the extent effect; data updates preserve the user's viewport.
}

export function ResultMap({
  viewerMode = false,
  finalNetwork,
  candidateNetwork,
  lhd,
  connectionPaths,
  buildingLocations,
  screenedOut,
  selectedCandidateId = null,
  onSelectCandidate,
  showCandidates = true,
  showFinalNetwork = true,
  showLhd = false,
  showPaths = true,
  showBuildings = true,
  showScreenedOut = false,
  fitRequest = 0,
  editableBoundingBox = null,
  bboxDrawingEnabled = false,
  onBoundingBoxChange,
  title = "Network map",
}: ResultMapProps) {
  useLocale();
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const mapLoadedRef = useRef(false);
  const fittedExtentRef = useRef("");
  const callbackRef = useRef(onSelectCandidate);
  const selectedRef = useRef(selectedCandidateId);
  const collectionsRef = useRef<FeatureCollection[]>([]);
  const visibilityRef = useRef<LayerVisibility>({
    candidates: showCandidates,
    finalNetwork: showFinalNetwork,
    lhd: showLhd,
    paths: showPaths,
    buildings: showBuildings,
    screenedOut: showScreenedOut,
  });
  const bboxRef = useRef<[number, number, number, number] | null>(null);
  const bboxDrawingEnabledRef = useRef(false);
  const bboxChangeRef = useRef(onBoundingBoxChange);
  const drawStartRef = useRef<[number, number] | null>(null);
  const resizeCornerRef = useRef<string | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState(false);
  const [mapRetry, setMapRetry] = useState(0);
  const preparedCollections = useMemo(
    () => [
      prepareFeatureCollection(finalNetwork),
      prepareFeatureCollection(candidateNetwork),
      prepareFeatureCollection(lhd),
      prepareFeatureCollection(connectionPaths),
      prepareFeatureCollection(buildingLocations),
      prepareFeatureCollection(screenedOut),
    ],
    [
      buildingLocations,
      candidateNetwork,
      connectionPaths,
      finalNetwork,
      lhd,
      screenedOut,
    ],
  );
  const rawCollections = useMemo(
    () => preparedCollections.map(({ collection }) => collection),
    [preparedCollections],
  );
  const collections = useMemo(
    () =>
      rawCollections.map((collection) => limitFeatureCollection(collection)),
    [rawCollections],
  );
  const mapLimitNotices = useMemo(() => {
    const labels = [
      "Final network",
      "Candidate areas",
      "Linear heat density",
      "Connection paths",
      "Buildings",
      "Screened-out edges",
    ];
    return preparedCollections.flatMap((prepared, index) => {
      const notices: string[] = [];
      if (prepared.malformedCollection) {
        notices.push(`${labels[index]} could not be read`);
      } else if (prepared.droppedFeatures > 0) {
        notices.push(
          `${labels[index]} skipped ${formatNumber(prepared.droppedFeatures)} malformed features`,
        );
      }
      if (prepared.collection.features.length > MAX_MAP_FEATURES) {
        notices.push(
          `${labels[index]} shows the first ${formatNumber(MAX_MAP_FEATURES)} of ${formatNumber(prepared.collection.features.length)} features`,
        );
      }
      return notices;
    });
  }, [preparedCollections]);
  const visibility = useMemo<LayerVisibility>(
    () => ({
      candidates: showCandidates,
      finalNetwork: showFinalNetwork,
      lhd: showLhd,
      paths: showPaths,
      buildings: showBuildings,
      screenedOut: showScreenedOut,
    }),
    [
      showBuildings,
      showCandidates,
      showFinalNetwork,
      showLhd,
      showPaths,
      showScreenedOut,
    ],
  );
  const extent = useMemo(
    () =>
      extentFor([
        visibility.finalNetwork ? collections[0] : emptyCollection,
        visibility.candidates ? collections[1] : emptyCollection,
        visibility.lhd ? collections[2] : emptyCollection,
        visibility.paths ? collections[3] : emptyCollection,
        visibility.buildings ? collections[4] : emptyCollection,
        visibility.screenedOut ? collections[5] : emptyCollection,
        boundingBoxCollection(editableBoundingBox),
      ]),
    [collections, visibility, editableBoundingBox],
  );

  callbackRef.current = onSelectCandidate;
  selectedRef.current = selectedCandidateId;
  collectionsRef.current = collections;
  visibilityRef.current = visibility;
  bboxRef.current = editableBoundingBox;
  bboxDrawingEnabledRef.current = bboxDrawingEnabled;
  bboxChangeRef.current = onBoundingBoxChange;

  useEffect(() => {
    let cancelled = false;
    setMapError(false);
    if (!mapContainer.current || typeof window === "undefined") return;

    void import("maplibre-gl")
      .then(({ default: MapLibre }) => {
        if (cancelled || !mapContainer.current) return;
        try {
          const map = new MapLibre.Map({
            container: mapContainer.current,
            style: "https://tiles.openfreemap.org/styles/dark",
            attributionControl: {
              compact: false,
              customAttribution:
                '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> (<a href="https://opendatacommons.org/licenses/odbl/1-0/">ODbL</a>)',
            },
            interactive: true,
          });
          mapRef.current = map;
          map.addControl(
            new MapLibre.NavigationControl({ showCompass: false }),
            "top-left",
          );
          map.on("load", () => {
            if (cancelled) return;
            try {
              const definitions = [
                [layerIds.network, collectionsRef.current[0]],
                [layerIds.candidates, collectionsRef.current[1]],
                [layerIds.lhd, collectionsRef.current[2]],
                [layerIds.paths, collectionsRef.current[3]],
                [layerIds.buildings, collectionsRef.current[4]],
                [layerIds.screenedOut, collectionsRef.current[5]],
              ] as const;
              definitions.forEach(([id, data]) => {
                map.addSource(id, {
                  type: "geojson",
                  data: sourceData(data) as never,
                });
              });
              map.addSource(layerIds.boundingBox, {
                type: "geojson",
                data: sourceData(
                  boundingBoxCollection(bboxRef.current),
                ) as never,
              });
              map.addSource(layerIds.boundingBoxHandles, {
                type: "geojson",
                data: sourceData(
                  boundingBoxHandleCollection(
                    bboxChangeRef.current ? bboxRef.current : null,
                  ),
                ) as never,
              });
              map.addLayer({
                id: "lhd-lines",
                type: "line",
                source: layerIds.lhd,
                layout: {
                  visibility: visibilityRef.current.lhd ? "visible" : "none",
                },
                paint: {
                  "line-color": [
                    "interpolate",
                    ["linear"],
                    ["coalesce", ["get", "linear_heat_density"], 0],
                    0,
                    "#1a237e",
                    3,
                    "#ff6f00",
                  ],
                  "line-opacity": 0.5,
                  "line-width": 1.5,
                },
              });
              map.addLayer({
                id: "candidate-lines",
                type: "line",
                source: layerIds.candidates,
                layout: {
                  visibility: visibilityRef.current.candidates
                    ? "visible"
                    : "none",
                },
                paint: {
                  "line-color": [
                    "match",
                    ["get", "decision"],
                    "connected",
                    "#00c853",
                    "rejected",
                    "#ff1744",
                    "current",
                    "#ffd600",
                    "#64748b",
                  ],
                  "line-opacity": 0.72,
                  "line-color-transition": { duration: 350 },
                  "line-width": 2,
                },
              });
              map.addLayer({
                id: "network-lines",
                type: "line",
                source: layerIds.network,
                layout: {
                  visibility: visibilityRef.current.finalNetwork
                    ? "visible"
                    : "none",
                },
                paint: {
                  "line-color": "#17324d",
                  "line-opacity": 0.95,
                  "line-width": 3,
                },
              });
              map.addLayer({
                id: "path-lines",
                type: "line",
                source: layerIds.paths,
                layout: {
                  visibility: visibilityRef.current.paths ? "visible" : "none",
                },
                paint: {
                  "line-color": "#00e676",
                  "line-opacity": 0.85,
                  "line-width": 2.5,
                  "line-dasharray": [2, 2],
                },
              });
              map.addLayer({
                id: "building-polygons",
                type: "fill",
                source: layerIds.buildings,
                layout: {
                  visibility: visibilityRef.current.buildings
                    ? "visible"
                    : "none",
                },
                paint: {
                  "fill-color": "#1d557d",
                  "fill-opacity": 0.22,
                  "fill-outline-color": "#1d557d",
                },
              });
              map.addLayer({
                id: "building-points",
                type: "circle",
                source: layerIds.buildings,
                layout: {
                  visibility: visibilityRef.current.buildings
                    ? "visible"
                    : "none",
                },
                paint: {
                  "circle-color": "#1d557d",
                  "circle-opacity": 0.8,
                  "circle-radius": 3,
                },
              });
              map.addLayer({
                id: "screened-out-lines",
                type: "line",
                source: layerIds.screenedOut,
                layout: {
                  visibility: visibilityRef.current.screenedOut
                    ? "visible"
                    : "none",
                },
                paint: {
                  "line-color": "#94a3b8",
                  "line-opacity": 0.7,
                  "line-dasharray": [1.5, 2],
                  "line-width": 1,
                },
              });
              map.addLayer({
                id: "study-area-bbox-fill",
                type: "fill",
                source: layerIds.boundingBox,
                paint: { "fill-color": "#2563eb", "fill-opacity": 0.1 },
              });
              map.addLayer({
                id: "study-area-bbox-line",
                type: "line",
                source: layerIds.boundingBox,
                paint: {
                  "line-color": "#2563eb",
                  "line-opacity": 0.95,
                  "line-width": 3,
                },
              });
              map.addLayer({
                id: "study-area-bbox-handles",
                type: "circle",
                source: layerIds.boundingBoxHandles,
                paint: {
                  "circle-color": "#ffffff",
                  "circle-radius": 7,
                  "circle-stroke-color": "#2563eb",
                  "circle-stroke-width": 3,
                },
              });
              map.addLayer({
                id: "selected-candidate-line",
                type: "line",
                source: layerIds.candidates,
                filter: [
                  "==",
                  ["get", "candidate_id"],
                  selectedRef.current ?? -999999,
                ],
                paint: {
                  "line-color": "#ffd600",
                  "line-opacity": 1,
                  "line-width": 4,
                },
              });
              map.on("click", "candidate-lines", (event) => {
                const value = event.features?.[0]?.properties?.candidate_id;
                const id = Number(value);
                if (Number.isFinite(id)) callbackRef.current?.(id);
              });
              const setEditableBoundingBox = (
                bbox: [number, number, number, number],
              ) => {
                const outline = map.getSource(layerIds.boundingBox);
                const handles = map.getSource(layerIds.boundingBoxHandles);
                if (
                  outline &&
                  "setData" in outline &&
                  typeof outline.setData === "function"
                ) {
                  (outline.setData as (value: unknown) => void)(
                    sourceData(boundingBoxCollection(bbox)),
                  );
                }
                if (
                  handles &&
                  "setData" in handles &&
                  typeof handles.setData === "function"
                ) {
                  (handles.setData as (value: unknown) => void)(
                    sourceData(boundingBoxHandleCollection(bbox)),
                  );
                }
              };
              map.on("mousedown", (event) => {
                const handle = map.queryRenderedFeatures(event.point, {
                  layers: ["study-area-bbox-handles"],
                })[0];
                const corner = handle?.properties?.corner;
                if (typeof corner === "string" && bboxRef.current) {
                  resizeCornerRef.current = corner;
                  map.dragPan.disable();
                  return;
                }
                if (!bboxDrawingEnabledRef.current) return;
                drawStartRef.current = [event.lngLat.lng, event.lngLat.lat];
                map.dragPan.disable();
              });
              map.on("mousemove", (event) => {
                const point: [number, number] = [
                  event.lngLat.lng,
                  event.lngLat.lat,
                ];
                const resizeCorner = resizeCornerRef.current;
                const start = drawStartRef.current;
                const next =
                  resizeCorner && bboxRef.current
                    ? resizeBoundingBox(bboxRef.current, resizeCorner, point)
                    : start && bboxDrawingEnabledRef.current
                      ? normalizedBoundingBox(start, point)
                      : null;
                if (next) setEditableBoundingBox(next);
              });
              map.on("mouseup", (event) => {
                const resizeCorner = resizeCornerRef.current;
                const start = drawStartRef.current;
                resizeCornerRef.current = null;
                drawStartRef.current = null;
                map.dragPan.enable();
                const point: [number, number] = [
                  event.lngLat.lng,
                  event.lngLat.lat,
                ];
                const next =
                  resizeCorner && bboxRef.current
                    ? resizeBoundingBox(bboxRef.current, resizeCorner, point)
                    : start && bboxDrawingEnabledRef.current
                      ? normalizedBoundingBox(start, point)
                      : null;
                if (next && next[0] < next[2] && next[1] < next[3])
                  bboxChangeRef.current?.(next);
              });
              mapLoadedRef.current = true;
              updateMap(
                map,
                collectionsRef.current,
                visibilityRef.current,
                selectedRef.current,
              );
              setMapReady(true);
            } catch {
              setMapError(true);
            }
          });
          map.on("error", () => setMapError(true));
        } catch {
          setMapError(true);
        }
      })
      .catch(() => setMapError(true));

    return () => {
      cancelled = true;
      mapLoadedRef.current = false;
      fittedExtentRef.current = "";
      mapRef.current?.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, [mapRetry]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoadedRef.current || !mapReady) return;
    updateMap(map, collections, visibility, selectedCandidateId);
  }, [collections, extent, mapReady, selectedCandidateId, visibility]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const source = map.getSource(layerIds.boundingBox);
    const handles = map.getSource(layerIds.boundingBoxHandles);
    if (source && "setData" in source && typeof source.setData === "function") {
      (source.setData as (value: unknown) => void)(
        sourceData(boundingBoxCollection(editableBoundingBox)),
      );
    }
    if (
      handles &&
      "setData" in handles &&
      typeof handles.setData === "function"
    ) {
      (handles.setData as (value: unknown) => void)(
        sourceData(
          boundingBoxHandleCollection(
            onBoundingBoxChange ? editableBoundingBox : null,
          ),
        ),
      );
    }
    map.getCanvas().style.cursor = bboxDrawingEnabled ? "crosshair" : "";
  }, [bboxDrawingEnabled, editableBoundingBox, mapReady, onBoundingBoxChange]);

  useEffect(() => {
    if (!mapReady || !extent) return;
    const key = `${extent.minX},${extent.minY},${extent.maxX},${extent.maxY}:${fitRequest}`;
    if (fittedExtentRef.current === key) return;
    fittedExtentRef.current = key;
    fitMap(mapRef.current, extent);
  }, [extent, fitRequest, mapReady]);

  const fit = () => fitMap(mapRef.current, extent);

  return (
    <Paper
      aria-label={tr(title)}
      component="section"
      elevation={0}
      className={viewerMode ? "viewer-result-map" : undefined}
      sx={{
        border: viewerMode ? 0 : 1,
        borderColor: "divider",
        overflow: "hidden",
        ...(viewerMode
          ? {
              height: "100%",
              display: "flex",
              flexDirection: "column",
              borderRadius: 0,
            }
          : {}),
      }}
    >
      <Stack
        alignItems={{ sm: "center", xs: "flex-start" }}
        direction={{ sm: "row", xs: "column" }}
        justifyContent="space-between"
        spacing={1}
        sx={{ p: 1, ...(viewerMode ? { display: "none" } : {}) }}
      >
        <Typography component="h2" sx={{ px: 1 }} variant="subtitle1">
          {tr(title)}
        </Typography>
        <Button onClick={fit} size="small" variant="outlined">
          {tr("Center map")}
        </Button>
      </Stack>
      {mapLimitNotices.length > 0 && (
        <Alert severity="warning" sx={{ borderRadius: 0 }}>
          {tr("Map display is limited: ")}
          {tr(mapLimitNotices.join("; "))}
          {tr(". The candidate table remains complete.")}
        </Alert>
      )}
      <Box
        sx={{
          height: viewerMode ? "100%" : { md: 480, xs: 320 },
          minHeight: 0,
          flex: viewerMode ? 1 : undefined,
          position: "relative",
        }}
      >
        <FallbackMap
          collections={collections}
          extent={extent}
          onSelectCandidate={onSelectCandidate}
          selectedCandidateId={selectedCandidateId}
          visibility={visibility}
        />
        {!extent && (
          <Box
            sx={{
              backgroundColor: "rgba(22,33,62,0.92)",
              left: "50%",
              p: 2,
              position: "absolute",
              top: "50%",
              transform: "translate(-50%, -50%)",
              zIndex: 2,
            }}
          >
            <Typography color="text.secondary">
              {tr("No spatial layer is available.")}
            </Typography>
          </Box>
        )}
        <Box
          aria-hidden={!mapReady}
          data-testid="maplibre-map"
          ref={mapContainer}
          sx={{
            inset: 0,
            opacity: mapReady && !mapError ? 1 : 0,
            pointerEvents: mapReady && !mapError ? "auto" : "none",
            position: "absolute",
          }}
        />
        {mapError && (
          <MapErrorOverlay
            message="Interactive map unavailable; the accessible map view remains available."
            onRetry={() => setMapRetry((value) => value + 1)}
          />
        )}
      </Box>
      <Stack
        aria-label={tr("Map legend")}
        direction="row"
        flexWrap="wrap"
        gap={1.5}
        role="list"
        sx={{ px: 2, py: 1 }}
      >
        {!viewerMode && (
          <LegendItem color="#17324d" label={tr("Final network")} />
        )}
        <LegendItem color="#00c853" label={tr("Connected candidate")} />
        <LegendItem color="#ff1744" label={tr("Rejected candidate")} />
        <LegendItem color="#ffd600" label={tr("Current candidate")} />
        <LegendItem color="#64748b" label={tr("Pending candidate")} />
        <LegendItem color="#00e676" label={tr("Connection path")} />
      </Stack>
    </Paper>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  useLocale();
  return (
    <Stack alignItems="center" direction="row" role="listitem" spacing={0.5}>
      <Box
        aria-hidden="true"
        sx={{ backgroundColor: color, borderRadius: 1, height: 3, width: 22 }}
      />
      <Typography variant="caption">{tr(label)}</Typography>
    </Stack>
  );
}
