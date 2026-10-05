"""Provider abstraction for place search.

Geocoding is intentionally not part of area validation.  Deployments may
override the default Nominatim endpoint, inject a test provider, or disable
search without changing the rest of the workflow.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class GeocodingProvider(Protocol):
    name: str

    def search(self, query: str, *, limit: int = 5) -> Sequence[Mapping[str, Any]]: ...


class GeocodingUnavailable(RuntimeError):
    """Raised when no provider has been configured."""


@dataclass(frozen=True, slots=True)
class DisabledGeocodingProvider:
    name: str = "disabled"

    def search(self, query: str, *, limit: int = 5) -> Sequence[Mapping[str, Any]]:
        del query, limit
        raise GeocodingUnavailable("No geocoding provider is configured for this workspace.")


@dataclass(frozen=True, slots=True)
class NominatimGeocodingProvider:
    """Small Nominatim adapter for interactive place search.

    The endpoint is configurable, and the provider makes no requests until a
    user submits a search. The request helper caches results and throttles each
    process to comply with the public service's limits for a single local app.
    """

    endpoint: str
    user_agent: str = "DH-COMPASS/0.1"
    name: str = "nominatim"

    def search(self, query: str, *, limit: int = 5) -> Sequence[Mapping[str, Any]]:
        from dh_compass.preprocessing.geocoding import search_location

        payload = search_location(query, endpoint=self.endpoint, user_agent=self.user_agent, limit=limit)
        features = payload.get("features", []) if isinstance(payload, Mapping) else []
        result: list[Mapping[str, Any]] = []
        for feature in features:
            if not isinstance(feature, Mapping):
                continue
            properties = feature.get("properties")
            geometry = feature.get("geometry")
            if not isinstance(properties, Mapping):
                properties = {}
            item: dict[str, Any] = {
                "display_name": str(properties.get("display_name") or query),
                "geometry": geometry if isinstance(geometry, Mapping) else None,
                "provider_id": properties.get("place_id"),
            }
            # Nominatim's GeoJSON result includes the place's bounding box.
            # Keep it so the UI can focus the map and let the user explicitly
            # adopt that extent as the study area.
            bbox = feature.get("bbox")
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                item["bbox"] = bbox
            result.append(item)
        return result


def provider_from_settings(settings: Any) -> GeocodingProvider:
    """Build an optional provider from settings without doing network I/O."""

    endpoint = getattr(settings, "geocoding_endpoint", None)
    if endpoint:
        return NominatimGeocodingProvider(endpoint=str(endpoint))
    return DisabledGeocodingProvider()


__all__ = [
    "DisabledGeocodingProvider",
    "GeocodingProvider",
    "GeocodingUnavailable",
    "NominatimGeocodingProvider",
    "provider_from_settings",
]
