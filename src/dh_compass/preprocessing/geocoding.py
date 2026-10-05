"""Explicit geocoding with persistent caching and single-process throttling."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import requests

from dh_compass.config import PathConfig

_lock = threading.Lock()
_last_request = 0.0


def search_location(
    query: str, *, endpoint: str, user_agent: str = "DH-COMPASS/0.1",
    limit: int = 5, cache_root: Path | None = None,
) -> dict:
    """Query a deliberately configured provider; deployment-wide limits apply.

    Use one process with the public Nominatim service. Multi-worker deployments
    must use a shared rate-limiting proxy or a separately licensed provider.
    """
    if not endpoint:
        raise ValueError("Configure a geocoding endpoint; see DATA_LICENSES.md.")
    request = {"endpoint": endpoint, "q": query, "limit": limit}
    key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    root = cache_root if cache_root is not None else PathConfig.from_project_root().cache_root
    path = root / "geocoding" / f"{key}.json"
    global _last_request
    with _lock:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        delay = 1.1 - (time.monotonic() - _last_request)
        if delay > 0:
            time.sleep(delay)
        _last_request = time.monotonic()
        response = requests.get(
            endpoint, params={"q": query, "format": "geojson", "limit": limit},
            headers={"User-Agent": user_agent}, timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Geocoding provider must return a GeoJSON object.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return payload
