import { tr } from "../../i18n/translate";
import { useLocale } from "../../i18n/locale";
import { Box } from "@mui/material";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { MapErrorOverlay } from "./MapErrorOverlay";

export interface BaseMapProps {
  title?: string;
  fallback: ReactNode;
  children?: ReactNode;
  height?: number | string;
  /** Increment to recreate the map after a provider or WebGL failure. */
  retryToken?: number;
  onMapReady?: (map: MapLibreMap | null) => void;
  onMapError?: (error: unknown) => void;
}

const DEFAULT_CENTER: [number, number] = [7.7, 51.35];
const DEFAULT_ZOOM = 8;

/**
 * Shared, deliberately boring map creation and failure containment.
 * Feature maps own their sources, layers, and interactions outside this
 * component; a broken basemap never replaces the surrounding workspace.
 */
export function BaseMap({
  title = "Map",
  fallback,
  children,
  height = "100%",
  retryToken = 0,
  onMapReady,
  onMapError,
}: BaseMapProps) {
  useLocale();
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const onMapReadyRef = useRef(onMapReady);
  const onMapErrorRef = useRef(onMapError);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  onMapReadyRef.current = onMapReady;
  onMapErrorRef.current = onMapError;

  useEffect(() => {
    let cancelled = false;
    setMapReady(false);
    setMapError(false);
    onMapReadyRef.current?.(null);

    if (!mapContainer.current || typeof window === "undefined") return;

    void import("maplibre-gl")
      .then(({ default: MapLibre }) => {
        if (cancelled || !mapContainer.current) return;
        try {
          const map = new MapLibre.Map({
            container: mapContainer.current,
            style: "https://tiles.openfreemap.org/styles/dark",
            center: DEFAULT_CENTER,
            zoom: DEFAULT_ZOOM,
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
            "top-right",
          );
          map.on("load", () => {
            if (cancelled) return;
            setMapReady(true);
            onMapReadyRef.current?.(map);
          });
          map.on("error", (event) => {
            if (cancelled) return;
            setMapError(true);
            onMapErrorRef.current?.(event);
          });
        } catch (error) {
          if (cancelled) return;
          setMapError(true);
          onMapErrorRef.current?.(error);
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setMapError(true);
        onMapErrorRef.current?.(error);
      });

    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
      setMapReady(false);
      onMapReadyRef.current?.(null);
    };
  }, [retryCount, retryToken]);

  const retry = () => setRetryCount((value) => value + 1);

  return (
    <Box
      aria-label={tr(title)}
      component="section"
      sx={{ height, minHeight: 0, position: "relative", width: "100%" }}
    >
      <Box
        aria-hidden={mapReady && !mapError}
        sx={{ inset: 0, position: "absolute" }}
      >
        {tr(fallback)}
      </Box>
      <Box
        aria-hidden={!mapReady || mapError}
        data-testid="maplibre-map"
        ref={mapContainer}
        sx={{
          inset: 0,
          opacity: mapReady && !mapError ? 1 : 0,
          pointerEvents: mapReady && !mapError ? "auto" : "none",
          position: "absolute",
          zIndex: 1,
        }}
      />
      {mapError && <MapErrorOverlay onRetry={retry} />}
      {tr(children)}
      <Box
        aria-hidden={mapReady && !mapError}
        sx={{
          bottom: 4,
          color: "text.secondary",
          display: mapReady && !mapError ? "none" : "block",
          fontSize: "0.7rem",
          left: 6,
          position: "absolute",
          zIndex: 3,
        }}
      >
        {tr("© OpenStreetMap contributors")}
      </Box>
    </Box>
  );
}
