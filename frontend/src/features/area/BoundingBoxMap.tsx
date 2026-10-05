import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Box, Stack, Typography } from "@mui/material";
import {
  useEffect,
  useReducer,
  useRef,
  useState,
  type PointerEvent,
} from "react";
import type { Map as MapLibreMap } from "maplibre-gl";

import { BaseMap } from "../../components/map/BaseMap";
import {
  bboxHandles,
  bboxPolygon,
  bboxReducer,
  clampPoint,
  initialBBoxInteractionState,
  interactionDraft,
  isActiveInteraction,
  isOrderedBBox,
  resizeBBox,
  type BBox,
  type BBoxCorner,
  type BBoxInteractionAction,
  type BBoxInteractionState,
  type BBoxLimits,
  type BBoxPoint,
  DEFAULT_BBOX_LIMITS,
  WORLD_BOUNDS,
} from "./bbox";

interface BoundingBoxMapProps {
  bbox?: BBox | null;
  onChange?: (bbox: BBox) => void;
  /** Compatibility name used by the former editable result map. */
  onBoundingBoxChange?: (bbox: BBox) => void;
  /** UI-only draft updates; never represents a submitted or saved bbox. */
  onDraftChange?: (bbox: BBox | null) => void;
  drawingEnabled?: boolean;
  onDrawingChange?: (drawing: boolean) => void;
  limits?: BBoxLimits;
  /** A search result can move the viewport without replacing the active bbox. */
  focusBBox?: BBox | null;
  /** Increment to explicitly fit the active bbox. */
  fitRequest?: number;
  height?: number | string;
  title?: string;
}

type InteractionEvent = {
  point?: { x: number; y: number };
  lngLat: { lng: number; lat: number };
  preventDefault?: () => void;
};

const BBOX_SOURCE = "area-selection-bbox";
const HANDLES_SOURCE = "area-selection-handles";
const BBOX_FILL_LAYER = "area-selection-bbox-fill";
const BBOX_LINE_LAYER = "area-selection-bbox-line";
const HANDLES_LAYER = "area-selection-bbox-handles";

function asPoint(event: InteractionEvent): BBoxPoint {
  return [event.lngLat.lng, event.lngLat.lat];
}

function isInsideBBox(point: BBoxPoint, bbox: BBox | null): boolean {
  if (!bbox) return false;
  return (
    point[0] >= bbox[0] &&
    point[0] <= bbox[2] &&
    point[1] >= bbox[1] &&
    point[1] <= bbox[3]
  );
}

function featureCorner(
  event: InteractionEvent,
  map: MapLibreMap,
): BBoxCorner | null {
  if (!event.point || !map.getLayer(HANDLES_LAYER)) return null;
  const feature = map.queryRenderedFeatures(event.point as never, {
    layers: [HANDLES_LAYER],
  })[0];
  const corner = feature?.properties?.corner;
  return corner === "southwest" ||
    corner === "northwest" ||
    corner === "northeast" ||
    corner === "southeast"
    ? corner
    : null;
}

function featureData(map: MapLibreMap, sourceId: string, data: unknown): void {
  const source = map.getSource(sourceId);
  if (source && "setData" in source && typeof source.setData === "function") {
    (source.setData as (value: unknown) => void)(data);
  }
}

function fitMap(map: MapLibreMap | null, bbox: BBox | null): void {
  if (!map || !bbox || !isOrderedBBox(bbox)) return;
  map.fitBounds(
    [
      [bbox[0], bbox[1]],
      [bbox[2], bbox[3]],
    ],
    { padding: 72, duration: 0 },
  );
}

function eventToFallbackPoint(
  event: PointerEvent<SVGSVGElement>,
  extent: BBox,
): BBoxPoint {
  const bounds = event.currentTarget.getBoundingClientRect();
  const x = bounds.width ? (event.clientX - bounds.left) / bounds.width : 0;
  const y = bounds.height ? (event.clientY - bounds.top) / bounds.height : 0;
  return [
    extent[0] + Math.min(Math.max(x, 0), 1) * (extent[2] - extent[0]),
    extent[3] - Math.min(Math.max(y, 0), 1) * (extent[3] - extent[1]),
  ];
}

function extentForFallback(
  bbox: BBox | null,
  focusBBox: BBox | null,
  coverage: BBox,
): BBox {
  const selected = focusBBox ?? bbox;
  if (!selected) return coverage;
  const west = selected[0];
  const south = selected[1];
  const east = selected[2];
  const north = selected[3];
  const paddingX = Math.max((east - west) * 0.08, 0.01);
  const paddingY = Math.max((north - south) * 0.08, 0.01);
  return [west - paddingX, south - paddingY, east + paddingX, north + paddingY];
}

function projectPoint(point: BBoxPoint, extent: BBox): BBoxPoint {
  const width = Math.max(extent[2] - extent[0], Number.EPSILON);
  const height = Math.max(extent[3] - extent[1], Number.EPSILON);
  return [
    ((point[0] - extent[0]) / width) * 100,
    100 - ((point[1] - extent[1]) / height) * 100,
  ];
}

function fallbackRectangle(bbox: BBox | null, extent: BBox) {
  if (!bbox) return null;
  const [west, north] = projectPoint([bbox[0], bbox[3]], extent);
  const [east, south] = projectPoint([bbox[2], bbox[1]], extent);
  return {
    x: Math.min(west, east),
    y: Math.min(north, south),
    width: Math.abs(east - west),
    height: Math.abs(south - north),
  };
}

function FallbackBBoxMap({
  bbox,
  draft,
  focusBBox,
  fitRequest,
  limits,
  drawing,
  onStart,
  onMove,
  onEnd,
  onCancel,
  onResizeKeyboard,
}: {
  bbox: BBox | null;
  draft: BBox | null;
  focusBBox: BBox | null;
  fitRequest: number;
  limits: BBoxLimits;
  drawing: boolean;
  onStart: (point: BBoxPoint, corner?: BBoxCorner) => void;
  onMove: (point: BBoxPoint) => void;
  onEnd: (point: BBoxPoint) => void;
  onCancel: () => void;
  onResizeKeyboard: (corner: BBoxCorner, direction: BBoxPoint) => void;
}) {
  useLocale();
  const activePointerRef = useRef<number | null>(null);
  const lastFitRequestRef = useRef(0);
  const [extent, setExtent] = useState<BBox>(() =>
    extentForFallback(null, null, limits.coverageBBox),
  );

  useEffect(() => {
    if (!focusBBox) return;
    setExtent(extentForFallback(null, focusBBox, limits.coverageBBox));
  }, [focusBBox, limits.coverageBBox]);

  useEffect(() => {
    if (fitRequest === 0 || fitRequest === lastFitRequestRef.current) return;
    lastFitRequestRef.current = fitRequest;
    setExtent(extentForFallback(bbox, null, limits.coverageBBox));
  }, [bbox, fitRequest, limits.coverageBBox]);
  const rectangle = fallbackRectangle(draft, extent);
  const handles = bbox
    ? (bboxHandles(bbox).features.map((feature) => ({
        corner: feature.properties.corner,
        point: feature.geometry.coordinates,
      })) as Array<{ corner: BBoxCorner; point: BBoxPoint }>)
    : [];
  const pointerDown = (event: PointerEvent<SVGSVGElement>) => {
    const target = event.target as Element;
    const rawCorner = target.getAttribute("data-corner");
    const corner =
      rawCorner === "southwest" ||
      rawCorner === "northwest" ||
      rawCorner === "northeast" ||
      rawCorner === "southeast"
        ? rawCorner
        : undefined;
    const point = eventToFallbackPoint(event, extent);
    onStart(point, corner);
    activePointerRef.current = event.pointerId;
    if (typeof event.currentTarget.setPointerCapture === "function") {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
  };
  const pointerMove = (event: PointerEvent<SVGSVGElement>) => {
    if (activePointerRef.current !== event.pointerId) return;
    onMove(eventToFallbackPoint(event, extent));
  };
  const pointerUp = (event: PointerEvent<SVGSVGElement>) => {
    if (activePointerRef.current === event.pointerId) {
      onEnd(eventToFallbackPoint(event, extent));
      if (typeof event.currentTarget.releasePointerCapture === "function") {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      activePointerRef.current = null;
    }
  };

  return (
    <Box
      sx={{
        backgroundColor: "#1a1a2e",
        height: "100%",
        position: "relative",
        width: "100%",
      }}
    >
      <svg
        aria-label={tr("Study area map fallback")}
        height="100%"
        onPointerCancel={() => {
          activePointerRef.current = null;
          onCancel();
        }}
        onPointerDown={pointerDown}
        onPointerMove={pointerMove}
        onPointerUp={pointerUp}
        role="img"
        style={{
          cursor: drawing ? "crosshair" : "default",
          touchAction: "none",
        }}
        viewBox="0 0 100 100"
        width="100%"
      >
        <rect fill="#1a1a2e" height="100" width="100" />
        <path
          d="M0 18H100M0 42H100M0 68H100M18 0V100M45 0V100M76 0V100"
          fill="none"
          stroke="#293448"
          strokeWidth="0.35"
        />
        <path
          d="M3 83C22 72 31 77 44 62S70 32 97 21"
          fill="none"
          stroke="#384359"
          strokeWidth="1.1"
        />
        {rectangle && (
          <rect
            data-bbox="true"
            fill="#2563eb"
            fillOpacity="0.16"
            height={rectangle.height}
            pointerEvents="none"
            stroke="#2563eb"
            strokeDasharray={drawing ? "2 1" : undefined}
            strokeWidth="0.75"
            width={rectangle.width}
            x={rectangle.x}
            y={rectangle.y}
          />
        )}
        {handles.map(({ corner, point }) => {
          const [x, y] = projectPoint(point, extent);
          return (
            <circle
              aria-label={tr(`Resize ${corner} corner`)}
              key={corner}
              cx={x}
              cy={y}
              data-corner={corner}
              fill="#fff"
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  onCancel();
                  return;
                }
                const step = event.shiftKey ? 0.01 : 0.001;
                if (event.key === "ArrowLeft") {
                  event.preventDefault();
                  onResizeKeyboard(corner, [-step, 0]);
                } else if (event.key === "ArrowRight") {
                  event.preventDefault();
                  onResizeKeyboard(corner, [step, 0]);
                } else if (event.key === "ArrowUp") {
                  event.preventDefault();
                  onResizeKeyboard(corner, [0, step]);
                } else if (event.key === "ArrowDown") {
                  event.preventDefault();
                  onResizeKeyboard(corner, [0, -step]);
                }
              }}
              r="3.5"
              role="button"
              stroke="#2563eb"
              strokeWidth="0.9"
              tabIndex={0}
            />
          );
        })}
      </svg>
      {drawing && (
        <Typography
          aria-live="polite"
          sx={{
            backgroundColor: "rgba(22,33,62,0.95)",
            left: 8,
            p: 0.75,
            position: "absolute",
            top: 8,
          }}
          variant="caption"
        >
          {tr(
            "Drag across the map to draw a new area. Press Escape to cancel.",
          )}
        </Typography>
      )}
    </Box>
  );
}

export function BoundingBoxMap({
  bbox = null,
  onChange,
  onBoundingBoxChange,
  onDraftChange,
  drawingEnabled = false,
  onDrawingChange,
  limits = DEFAULT_BBOX_LIMITS,
  focusBBox = null,
  fitRequest = 0,
  height = "100%",
  title = "Study area map",
}: BoundingBoxMapProps) {
  useLocale();
  const [state, dispatch] = useReducer(
    bboxReducer,
    bbox,
    initialBBoxInteractionState,
  );
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const [keyboardDrawing, setKeyboardDrawing] = useState(false);
  const mapRef = useRef<MapLibreMap | null>(null);
  const stateRef = useRef<BBoxInteractionState>(state);
  const bboxRef = useRef<BBox | null>(bbox);
  const bboxPropRef = useRef<BBox | null>(bbox);
  const limitsRef = useRef(limits);
  const onChangeRef = useRef(
    onChange ?? onBoundingBoxChange ?? (() => undefined),
  );
  const onDraftChangeRef = useRef(onDraftChange);
  const onDrawingChangeRef = useRef(onDrawingChange);
  const drawingRef = useRef(drawingEnabled || keyboardDrawing);
  const dragPanWasEnabledRef = useRef(true);
  const lastFocusRef = useRef<string | null>(null);
  const lastFitRequestRef = useRef(0);

  stateRef.current = state;
  if (bboxPropRef.current !== bbox) {
    bboxPropRef.current = bbox;
    if (!isActiveInteraction(stateRef.current)) bboxRef.current = bbox;
  }
  limitsRef.current = limits;
  onChangeRef.current = onChange ?? onBoundingBoxChange ?? (() => undefined);
  onDraftChangeRef.current = onDraftChange;
  onDrawingChangeRef.current = onDrawingChange;
  const drawing = drawingEnabled || keyboardDrawing;
  drawingRef.current = drawing;
  const draft = interactionDraft(state);

  useEffect(() => {
    if (isActiveInteraction(stateRef.current)) return;
    if (stateRef.current.kind === "idle" && stateRef.current.bbox === bbox) {
      return;
    }
    dispatch({ type: "sync", bbox });
  }, [bbox]);

  const setDrawingMode = (value: boolean) => {
    setKeyboardDrawing(value);
    onDrawingChangeRef.current?.(value);
  };

  const transition = (action: BBoxInteractionAction): BBoxInteractionState => {
    const next = bboxReducer(stateRef.current, action);
    stateRef.current = next;
    if (action.type === "commit" || action.type === "sync") {
      bboxRef.current = action.bbox;
    }
    dispatch(action);
    return next;
  };

  const disableMapPan = (currentMap: MapLibreMap) => {
    dragPanWasEnabledRef.current = currentMap.dragPan.isEnabled();
    currentMap.dragPan.disable();
  };

  const restoreMapPan = (currentMap: MapLibreMap) => {
    if (dragPanWasEnabledRef.current) currentMap.dragPan.enable();
  };

  const startInteraction = (point: BBoxPoint, corner?: BBoxCorner) => {
    const clamped = clampPoint(point, WORLD_BOUNDS);
    const current = bboxRef.current;
    if (corner && current) {
      transition({ type: "begin-resizing", corner, previous: current });
      onDraftChangeRef.current?.(current);
      return;
    }
    if (drawingRef.current) {
      const next = transition({
        type: "begin-drawing",
        start: clamped,
        previous: current,
      });
      onDraftChangeRef.current?.(interactionDraft(next));
      return;
    }
    if (current && isInsideBBox(clamped, current)) {
      transition({ type: "begin-moving", origin: clamped, previous: current });
      onDraftChangeRef.current?.(current);
    }
  };

  const updateInteraction = (point: BBoxPoint) => {
    const current = stateRef.current;
    if (!isActiveInteraction(current)) return;
    const clamped = clampPoint(point, WORLD_BOUNDS);
    const action: BBoxInteractionAction = {
      type: "update",
      point: clamped,
      bounds: limitsRef.current.coverageBBox,
    };
    const next = transition(action);
    const nextDraft = interactionDraft(next);
    onDraftChangeRef.current?.(nextDraft);
    if (mapRef.current && nextDraft) {
      featureData(mapRef.current, BBOX_SOURCE, bboxPolygon(nextDraft));
      featureData(mapRef.current, HANDLES_SOURCE, bboxHandles(nextDraft));
    }
  };

  const endInteraction = (point: BBoxPoint) => {
    const current = stateRef.current;
    if (!isActiveInteraction(current)) return;
    const clamped = clampPoint(point, WORLD_BOUNDS);
    const updated = bboxReducer(current, {
      type: "update",
      point: clamped,
      bounds: limitsRef.current.coverageBBox,
    });
    const nextDraft = interactionDraft(updated);
    const wasDrawing = current.kind === "drawing";
    if (
      !nextDraft ||
      nextDraft[0] >= nextDraft[2] ||
      nextDraft[1] >= nextDraft[3]
    ) {
      transition({
        type: "invalid",
        reason: "Drag across two different corners to create a rectangle.",
      });
      onDraftChangeRef.current?.(null);
      if (wasDrawing) setDrawingMode(false);
      return;
    }
    transition({ type: "commit", bbox: nextDraft });
    onChangeRef.current(nextDraft);
    onDraftChangeRef.current?.(null);
    if (wasDrawing) setDrawingMode(false);
  };

  const cancelInteraction = () => {
    const active = isActiveInteraction(stateRef.current);
    const invalid = stateRef.current.kind === "invalid";
    if (!active && !invalid && !drawingRef.current) return;
    if (active || invalid) transition({ type: "cancel" });
    onDraftChangeRef.current?.(null);
    setDrawingMode(false);
    if (mapRef.current) restoreMapPan(mapRef.current);
  };

  const startInteractionRef = useRef(startInteraction);
  const updateInteractionRef = useRef(updateInteraction);
  const endInteractionRef = useRef(endInteraction);
  const cancelInteractionRef = useRef(cancelInteraction);
  const previousDrawingEnabledRef = useRef(drawingEnabled);
  startInteractionRef.current = startInteraction;
  updateInteractionRef.current = updateInteraction;
  endInteractionRef.current = endInteraction;
  cancelInteractionRef.current = cancelInteraction;

  useEffect(() => {
    if (
      previousDrawingEnabledRef.current &&
      !drawingEnabled &&
      isActiveInteraction(stateRef.current) &&
      stateRef.current.kind === "drawing"
    ) {
      cancelInteractionRef.current();
    }
    previousDrawingEnabledRef.current = drawingEnabled;
  }, [drawingEnabled]);

  const resizeByKeyboard = (corner: BBoxCorner, direction: BBoxPoint) => {
    const current = bboxRef.current;
    if (!current) return;
    const [west, south, east, north] = current;
    const points: Record<BBoxCorner, BBoxPoint> = {
      southwest: [west + direction[0], south + direction[1]],
      northwest: [west + direction[0], north + direction[1]],
      northeast: [east + direction[0], north + direction[1]],
      southeast: [east + direction[0], south + direction[1]],
    };
    const next = resizeBBox(current, corner, points[corner]);
    if (next[0] >= next[2] || next[1] >= next[3]) return;
    transition({ type: "commit", bbox: next });
    onChangeRef.current(next);
    onDraftChangeRef.current?.(null);
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tagName = target?.tagName.toLowerCase();
      const inInput =
        tagName === "input" ||
        tagName === "textarea" ||
        tagName === "select" ||
        target?.isContentEditable;
      if (event.key === "Escape") {
        if (
          drawingRef.current ||
          isActiveInteraction(stateRef.current) ||
          stateRef.current.kind === "invalid"
        ) {
          event.preventDefault();
          cancelInteractionRef.current();
        }
        return;
      }
      if (!inInput && event.key.toLowerCase() === "r") {
        event.preventDefault();
        setDrawingMode(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    mapRef.current = map;
    if (!map) return;
    const addLayers = () => {
      if (!map.getSource(BBOX_SOURCE)) {
        map.addSource(BBOX_SOURCE, {
          type: "geojson",
          data: bboxPolygon(interactionDraft(stateRef.current)) as never,
        });
      }
      if (!map.getSource(HANDLES_SOURCE)) {
        map.addSource(HANDLES_SOURCE, {
          type: "geojson",
          data: bboxHandles(interactionDraft(stateRef.current)) as never,
        });
      }
      if (!map.getLayer(BBOX_FILL_LAYER)) {
        map.addLayer({
          id: BBOX_FILL_LAYER,
          type: "fill",
          source: BBOX_SOURCE,
          paint: { "fill-color": "#2563eb", "fill-opacity": 0.14 },
        });
      }
      if (!map.getLayer(BBOX_LINE_LAYER)) {
        map.addLayer({
          id: BBOX_LINE_LAYER,
          type: "line",
          source: BBOX_SOURCE,
          paint: {
            "line-color": "#2563eb",
            "line-opacity": 0.95,
            "line-width": 3,
          },
        });
      }
      if (!map.getLayer(HANDLES_LAYER)) {
        map.addLayer({
          id: HANDLES_LAYER,
          type: "circle",
          source: HANDLES_SOURCE,
          paint: {
            "circle-color": "#ffffff",
            "circle-radius": 9,
            "circle-stroke-color": "#2563eb",
            "circle-stroke-width": 3,
          },
        });
      }
    };
    addLayers();
    fitMap(map, bboxRef.current);

    const start = (event: InteractionEvent) => {
      const point = asPoint(event);
      const corner = featureCorner(event, map);
      const current = bboxRef.current;
      if (!corner && !drawingRef.current && !isInsideBBox(point, current))
        return;
      event.preventDefault?.();
      disableMapPan(map);
      startInteractionRef.current(point, corner ?? undefined);
    };
    const move = (event: InteractionEvent) => {
      if (!isActiveInteraction(stateRef.current)) return;
      event.preventDefault?.();
      updateInteractionRef.current(asPoint(event));
    };
    const end = (event: InteractionEvent) => {
      if (!isActiveInteraction(stateRef.current)) return;
      event.preventDefault?.();
      endInteractionRef.current(asPoint(event));
      restoreMapPan(map);
    };
    const finishOutside = (event: MouseEvent) => {
      if (!isActiveInteraction(stateRef.current)) return;
      const rect = map.getCanvas().getBoundingClientRect();
      const location = map.unproject([
        event.clientX - rect.left,
        event.clientY - rect.top,
      ]);
      endInteractionRef.current([location.lng, location.lat]);
      restoreMapPan(map);
    };
    const finishTouchOutside = (event: TouchEvent) => {
      const touch = event.changedTouches[0];
      if (!touch || !isActiveInteraction(stateRef.current)) return;
      const rect = map.getCanvas().getBoundingClientRect();
      const location = map.unproject([
        touch.clientX - rect.left,
        touch.clientY - rect.top,
      ]);
      endInteractionRef.current([location.lng, location.lat]);
      restoreMapPan(map);
    };
    const listen = (
      name: string,
      handler: (event: InteractionEvent) => void,
    ) => {
      map.on(name as never, handler as never);
    };
    const unlisten = (
      name: string,
      handler: (event: InteractionEvent) => void,
    ) => {
      map.off(name as never, handler as never);
    };
    listen("mousedown", start);
    listen("mousemove", move);
    listen("mouseup", end);
    listen("touchstart", start);
    listen("touchmove", move);
    listen("touchend", end);
    window.addEventListener("mouseup", finishOutside);
    window.addEventListener("touchend", finishTouchOutside);

    return () => {
      unlisten("mousedown", start);
      unlisten("mousemove", move);
      unlisten("mouseup", end);
      unlisten("touchstart", start);
      unlisten("touchmove", move);
      unlisten("touchend", end);
      window.removeEventListener("mouseup", finishOutside);
      window.removeEventListener("touchend", finishTouchOutside);
      mapRef.current = null;
    };
  }, [map]);

  useEffect(() => {
    if (!map) return;
    const current = interactionDraft(state);
    featureData(map, BBOX_SOURCE, bboxPolygon(current));
    featureData(map, HANDLES_SOURCE, bboxHandles(current));
    map.getCanvas().style.cursor = drawing ? "crosshair" : "";
  }, [drawing, map, state]);

  useEffect(() => {
    if (!focusBBox) {
      lastFocusRef.current = null;
      return;
    }
    if (!map) return;
    const focusKey = focusBBox.join(",");
    if (lastFocusRef.current === focusKey) return;
    lastFocusRef.current = focusKey;
    fitMap(map, focusBBox);
  }, [focusBBox, map]);

  useEffect(() => {
    if (!map || fitRequest === 0 || fitRequest === lastFitRequestRef.current) {
      return;
    }
    lastFitRequestRef.current = fitRequest;
    fitMap(map, bbox);
  }, [bbox, fitRequest, map]);

  const fallback = (
    <FallbackBBoxMap
      bbox={bbox}
      draft={draft}
      focusBBox={focusBBox}
      fitRequest={fitRequest}
      limits={limits}
      drawing={drawing}
      onStart={startInteraction}
      onMove={updateInteraction}
      onEnd={endInteraction}
      onCancel={cancelInteraction}
      onResizeKeyboard={resizeByKeyboard}
    />
  );

  return (
    <Box
      aria-label={tr(title)}
      onKeyDown={(event) => {
        if (event.key === "Escape") cancelInteraction();
      }}
      sx={{ height, minHeight: 0, position: "relative", width: "100%" }}
    >
      <BaseMap
        fallback={fallback}
        height="100%"
        onMapReady={setMap}
        title={tr(title)}
      />
      {state.kind === "invalid" && (
        <Stack
          aria-live="polite"
          sx={{
            backgroundColor: "rgba(22,33,62,0.95)",
            border: 1,
            borderColor: "error.main",
            borderRadius: 1,
            bottom: 8,
            left: 8,
            p: 1,
            position: "absolute",
            zIndex: 5,
          }}
        >
          <Typography color="error.main" variant="body2">
            {tr(state.reason)}
          </Typography>
        </Stack>
      )}
      <Typography
        aria-live="polite"
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
        {tr(
          drawing
            ? "Drawing mode is active. Drag from one corner to the opposite corner."
            : "Study area rectangle. Drag inside it to move it or use a corner handle to resize it.",
        )}
      </Typography>
    </Box>
  );
}

export type { BoundingBoxMapProps };
