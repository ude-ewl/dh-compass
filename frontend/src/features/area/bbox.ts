import { formatNumericValue } from "../../i18n/number";
export type BBox = [number, number, number, number];
export type BBoxPoint = [number, number];
export type BBoxCorner = "southwest" | "northwest" | "northeast" | "southeast";

export interface BBoxLimits {
  coverageBBox: BBox;
  minAreaKm2: number;
  maxAreaKm2: number;
}

export interface BBoxValidationIssue {
  code: string;
  message: string;
  remediation?: string;
}

export interface BBoxValidation {
  bbox: BBox | null;
  areaKm2: number | null;
  issues: BBoxValidationIssue[];
}

/** The coarse NRW envelope advertised by the calculation contract. */
export const DEFAULT_BBOX_LIMITS: BBoxLimits = {
  coverageBBox: [5.866, 50.322, 9.531, 52.531],
  minAreaKm2: 0.01,
  maxAreaKm2: 2_500,
};

export const WORLD_BOUNDS: BBox = [-180, -90, 180, 90];

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function asNumbers(value: unknown): number[] | null {
  if (!Array.isArray(value) || value.length !== 4) return null;
  const numbers = value.map((item) =>
    typeof item === "number" && Number.isFinite(item) ? item : Number.NaN,
  );
  return numbers.every((item) => Number.isFinite(item)) ? numbers : null;
}

/**
 * Normalize both drag directions into west, south, east, north order.
 * Keeping this as a pure function makes pointer behavior easy to characterize.
 */
export function normalizeBBox(start: BBoxPoint, end: BBoxPoint): BBox {
  return [
    Math.min(start[0], end[0]),
    Math.min(start[1], end[1]),
    Math.max(start[0], end[0]),
    Math.max(start[1], end[1]),
  ];
}

export function isOrderedBBox(value: unknown): value is BBox {
  const numbers = asNumbers(value);
  return Boolean(
    numbers &&
    numbers[0] >= -180 &&
    numbers[2] <= 180 &&
    numbers[1] >= -90 &&
    numbers[3] <= 90 &&
    numbers[0] < numbers[2] &&
    numbers[1] < numbers[3],
  );
}

/** Approximate WGS84 rectangle area, matching the server contract. */
export function bboxAreaKm2(bbox: BBox): number {
  const [west, south, east, north] = bbox;
  const latitudeKm = 111.32;
  const meanLatitude = ((south + north) / 2) * (Math.PI / 180);
  const widthKm = (east - west) * latitudeKm * Math.cos(meanLatitude);
  const heightKm = (north - south) * latitudeKm;
  return Math.abs(widthKm * heightKm);
}

/**
 * Validate exact-coordinate input without throwing on partial form values.
 * The issue codes mirror the calculation contract so a server response can be
 * displayed beside the same controls.
 */
export function validateBBox(
  value: unknown,
  limits: BBoxLimits = DEFAULT_BBOX_LIMITS,
): BBoxValidation {
  const numbers = asNumbers(value);
  if (!Array.isArray(value) || value.length !== 4) {
    return {
      bbox: null,
      areaKm2: null,
      issues: [
        {
          code: "BBOX_SHAPE_INVALID",
          message:
            "The bounding box must contain west, south, east, and north.",
          remediation:
            "Provide four coordinates in west, south, east, north order.",
        },
      ],
    };
  }
  if (!numbers) {
    return {
      bbox: null,
      areaKm2: null,
      issues: [
        {
          code: "BBOX_COORDINATES_INVALID",
          message: "Enter four finite longitude and latitude values.",
          remediation: "Use numeric longitude and latitude values.",
        },
      ],
    };
  }

  const bbox = numbers as BBox;
  const [west, south, east, north] = bbox;
  const issues: BBoxValidationIssue[] = [];
  if (
    west < WORLD_BOUNDS[0] ||
    east > WORLD_BOUNDS[2] ||
    south < WORLD_BOUNDS[1] ||
    north > WORLD_BOUNDS[3]
  ) {
    issues.push({
      code: "BBOX_WORLD_BOUNDS",
      message: "Coordinates must use longitude −180…180 and latitude −90…90.",
      remediation: "Check longitude/latitude order and values.",
    });
  }
  if (west >= east) {
    issues.push({
      code: "BBOX_LONGITUDE_ORDER",
      message: "The west longitude must be smaller than the east longitude.",
      remediation: "Swap the horizontal corners or edit the exact extent.",
    });
  }
  if (south >= north) {
    issues.push({
      code: "BBOX_LATITUDE_ORDER",
      message: "The south latitude must be smaller than the north latitude.",
      remediation: "Swap the vertical corners or edit the exact extent.",
    });
  }
  if (issues.length > 0) {
    return { bbox, areaKm2: null, issues };
  }

  const [coverageWest, coverageSouth, coverageEast, coverageNorth] =
    limits.coverageBBox;
  if (
    west < coverageWest ||
    south < coverageSouth ||
    east > coverageEast ||
    north > coverageNorth
  ) {
    issues.push({
      code: "BBOX_OUTSIDE_NRW",
      message: "The selected area must be inside the supported NRW coverage.",
      remediation: "Choose an area within the supported NRW extent.",
    });
  }

  const areaKm2 = bboxAreaKm2(bbox);
  if (areaKm2 < limits.minAreaKm2) {
    issues.push({
      code: "BBOX_TOO_SMALL",
      message: `The selected area is smaller than ${formatArea(limits.minAreaKm2)}.`,
      remediation: "Draw a slightly larger study area.",
    });
  }
  if (areaKm2 > limits.maxAreaKm2) {
    issues.push({
      code: "BBOX_TOO_LARGE",
      message: `The selected area is larger than ${formatArea(limits.maxAreaKm2)}.`,
      remediation: "Draw a smaller study area or split the analysis.",
    });
  }
  return { bbox, areaKm2, issues };
}

function formatArea(value: number): string {
  return `${formatNumericValue(value, { maximumFractionDigits: 2 })} km²`;
}

export function formatAreaKm2(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const maximumFractionDigits = value < 1 ? 3 : 1;
  return `${formatNumericValue(value, { maximumFractionDigits })} km²`;
}

export function formatCoordinate(value: number): string {
  return Number.isFinite(value) ? String(Number(value.toFixed(6))) : "";
}

export function bboxPolygon(bbox: BBox | null): {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: { type: "Polygon"; coordinates: number[][][] };
    properties: Record<string, string>;
  }>;
} {
  if (!bbox) return { type: "FeatureCollection", features: [] };
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
  };
}

export function bboxHandles(bbox: BBox | null): {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: { type: "Point"; coordinates: BBoxPoint };
    properties: { corner: BBoxCorner };
  }>;
} {
  if (!bbox) return { type: "FeatureCollection", features: [] };
  const [west, south, east, north] = bbox;
  const corners: Array<[BBoxCorner, BBoxPoint]> = [
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
  };
}

export function resizeBBox(
  bbox: BBox,
  corner: BBoxCorner,
  point: BBoxPoint,
): BBox {
  const [west, south, east, north] = bbox;
  if (corner === "southwest") return normalizeBBox(point, [east, north]);
  if (corner === "northwest")
    return normalizeBBox([point[0], south], [east, point[1]]);
  if (corner === "northeast") return normalizeBBox([west, south], point);
  return normalizeBBox([west, point[1]], [point[0], north]);
}

export function moveBBox(
  bbox: BBox,
  origin: BBoxPoint,
  point: BBoxPoint,
  bounds: BBox = WORLD_BOUNDS,
): BBox {
  const [west, south, east, north] = bbox;
  const deltaX = point[0] - origin[0];
  const deltaY = point[1] - origin[1];
  const width = east - west;
  const height = north - south;
  const [minX, minY, maxX, maxY] = bounds;
  const clampedWest = Math.min(
    Math.max(west + deltaX, minX),
    Math.max(minX, maxX - width),
  );
  const clampedSouth = Math.min(
    Math.max(south + deltaY, minY),
    Math.max(minY, maxY - height),
  );
  return [
    clampedWest,
    clampedSouth,
    clampedWest + width,
    clampedSouth + height,
  ];
}

export function clampPoint(
  point: BBoxPoint,
  bounds: BBox = WORLD_BOUNDS,
): BBoxPoint {
  return [
    Math.min(Math.max(point[0], bounds[0]), bounds[2]),
    Math.min(Math.max(point[1], bounds[1]), bounds[3]),
  ];
}

export type BBoxInteractionState =
  | { kind: "idle"; bbox: BBox | null }
  | {
      kind: "drawing";
      start: BBoxPoint;
      draft: BBox;
      previous: BBox | null;
    }
  | {
      kind: "resizing";
      corner: BBoxCorner;
      draft: BBox;
      previous: BBox;
    }
  | {
      kind: "moving";
      origin: BBoxPoint;
      draft: BBox;
      previous: BBox;
    }
  | {
      kind: "invalid";
      bbox: BBox | null;
      reason: string;
      previous: BBox | null;
    }
  | { kind: "submitting"; bbox: BBox };

export type BBoxInteractionAction =
  | { type: "sync"; bbox: BBox | null }
  | { type: "begin-drawing"; start: BBoxPoint; previous: BBox | null }
  | { type: "begin-resizing"; corner: BBoxCorner; previous: BBox }
  | { type: "begin-moving"; origin: BBoxPoint; previous: BBox }
  | { type: "update"; point: BBoxPoint; bounds?: BBox }
  | { type: "commit"; bbox: BBox }
  | { type: "invalid"; reason: string }
  | { type: "cancel" }
  | { type: "submitting"; bbox: BBox }
  | { type: "submitted" };

export const initialBBoxInteractionState = (
  bbox: BBox | null = null,
): BBoxInteractionState => ({ kind: "idle", bbox });

/** Reducer for all rectangle interaction modes. */
export function bboxReducer(
  state: BBoxInteractionState,
  action: BBoxInteractionAction,
): BBoxInteractionState {
  switch (action.type) {
    case "sync":
      return { kind: "idle", bbox: action.bbox };
    case "begin-drawing":
      return {
        kind: "drawing",
        start: action.start,
        draft: normalizeBBox(action.start, action.start),
        previous: action.previous,
      };
    case "begin-resizing":
      return {
        kind: "resizing",
        corner: action.corner,
        draft: action.previous,
        previous: action.previous,
      };
    case "begin-moving":
      return {
        kind: "moving",
        origin: action.origin,
        draft: action.previous,
        previous: action.previous,
      };
    case "update": {
      if (state.kind === "drawing") {
        return {
          ...state,
          draft: normalizeBBox(state.start, action.point),
        };
      }
      if (state.kind === "resizing") {
        return {
          ...state,
          draft: resizeBBox(state.previous, state.corner, action.point),
        };
      }
      if (state.kind === "moving") {
        return {
          ...state,
          draft: moveBBox(
            state.previous,
            state.origin,
            action.point,
            action.bounds ?? WORLD_BOUNDS,
          ),
        };
      }
      return state;
    }
    case "commit":
      return { kind: "idle", bbox: action.bbox };
    case "invalid":
      return {
        kind: "invalid",
        bbox:
          state.kind === "idle" ||
          state.kind === "submitting" ||
          state.kind === "invalid"
            ? state.bbox
            : state.draft,
        reason: action.reason,
        previous:
          state.kind === "idle" ||
          state.kind === "submitting" ||
          state.kind === "invalid"
            ? state.kind === "invalid"
              ? state.previous
              : state.bbox
            : state.previous,
      };
    case "cancel":
      if (state.kind === "drawing" || state.kind === "invalid") {
        return { kind: "idle", bbox: state.previous };
      }
      if (state.kind === "resizing" || state.kind === "moving") {
        return { kind: "idle", bbox: state.previous };
      }
      return state.kind === "submitting"
        ? { kind: "idle", bbox: state.bbox }
        : state;
    case "submitting":
      return { kind: "submitting", bbox: action.bbox };
    case "submitted":
      return state.kind === "submitting"
        ? { kind: "idle", bbox: state.bbox }
        : state;
    default:
      return state;
  }
}

export function interactionDraft(state: BBoxInteractionState): BBox | null {
  if (state.kind === "idle" || state.kind === "submitting") return state.bbox;
  if (state.kind === "invalid") return state.bbox;
  return state.draft;
}

export function isActiveInteraction(state: BBoxInteractionState): boolean {
  return (
    state.kind === "drawing" ||
    state.kind === "resizing" ||
    state.kind === "moving"
  );
}

export function isFinitePoint(point: BBoxPoint): boolean {
  return isFiniteNumber(point[0]) && isFiniteNumber(point[1]);
}
