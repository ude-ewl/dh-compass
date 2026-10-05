"""Area-specific historical weather, acquired only at explicit runtime boundaries."""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LOGGER = logging.getLogger(__name__)
ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"
CACHE_VERSION = 1
ATTRIBUTION = (
    "Weather: Open-Meteo Historical Weather API; ERA5-Land, Copernicus/ECMWF. "
    "Data licensed under CC BY 4.0; temperatures downscaled by Open-Meteo."
)


class WeatherError(RuntimeError):
    """Weather could not be acquired or did not pass validation."""


@dataclass(frozen=True)
class WeatherData:
    data: pd.DataFrame
    provenance: dict


def weather_request(config) -> dict:
    west, south, east, north = config.scenario.bbox
    year = config.demand.slp_year
    if not 1950 <= year < datetime.now(timezone.utc).year:
        raise WeatherError("Weather year must be a completed calendar year from 1950 onward.")
    return {
        "provider": "open-meteo",
        "endpoint": ENDPOINT,
        "latitude": round((south + north) / 2, 6),
        "longitude": round((west + east) / 2, 6),
        "start_date": f"{year}-01-01",
        "end_date": f"{year}-12-31",
        "hourly": "temperature_2m",
        "models": "era5_land",
        "timezone": "UTC",
        "temperature_unit": "celsius",
        "cell_selection": "land",
        "elevation_policy": "provider_dem",
        "cache_version": CACHE_VERSION,
    }


def _digest(value) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def weather_cache_path(config) -> Path:
    return config.paths.cache_root / "weather" / f"{_digest(weather_request(config))}.json"


def _validate_response(response: dict, request: dict) -> pd.DataFrame:
    try:
        if not isinstance(response, dict):
            raise ValueError("weather response must be a JSON object")
        if response.get("utc_offset_seconds") != 0:
            raise ValueError("weather timestamps must use UTC")
        if response["hourly_units"]["temperature_2m"] != "°C":
            raise ValueError("weather temperatures must use Celsius")
        hourly = response["hourly"]
        timestamps = pd.DatetimeIndex(pd.to_datetime(hourly["time"], utc=True))
        year = int(request["start_date"][:4])
        expected = pd.date_range(
            f"{year}-01-01", f"{year + 1}-01-01", freq="h", tz="UTC", inclusive="left"
        )
        if not timestamps.equals(expected):
            raise ValueError("weather must contain every hour of the requested year exactly once")
        values = hourly["temperature_2m"]
        if len(values) != len(expected) or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in values
        ):
            raise ValueError("weather temperatures contain missing or non-finite values")
        for field in ("latitude", "longitude", "elevation"):
            if not math.isfinite(float(response[field])):
                raise ValueError(f"invalid weather {field}")
        return pd.DataFrame({"datetime": timestamps, "temperature": values})
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise WeatherError(f"Invalid Open-Meteo weather data: {exc}") from exc


def _decode_cache(document: dict, request: dict) -> WeatherData:
    try:
        if not isinstance(document, dict):
            raise ValueError("weather cache must be a JSON object")
        if document["request"] != request:
            raise WeatherError("Weather cache belongs to another location or request.")
        response = document["response"]
        checksum = _digest(response)
        if checksum != document["checksum"]:
            raise WeatherError("Weather cache checksum does not match its contents.")
        data = _validate_response(response, request)
        provenance = {
            "provider": "open-meteo",
            "model": request["models"],
            "weather_year": int(request["start_date"][:4]),
            "requested_coordinates": {
                "latitude": request["latitude"], "longitude": request["longitude"]
            },
            "grid_coordinates": {
                "latitude": response["latitude"], "longitude": response["longitude"]
            },
            "elevation_m": response["elevation"],
            "elevation_policy": request["elevation_policy"],
            "timezone": "UTC",
            "unit": "°C",
            "hours": len(data),
            "fetched_at": document["fetched_at"],
            "checksum": checksum,
            "cache_version": CACHE_VERSION,
            "source_url": "https://open-meteo.com/en/docs/historical-weather-api",
            "licence": "CC BY 4.0",
            "attribution": ATTRIBUTION,
        }
        return WeatherData(data=data, provenance=provenance)
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherError(f"Invalid weather cache: {exc}") from exc


def read_weather_cache(config) -> WeatherData:
    """Validate an existing cache without performing any network access."""
    return read_weather_cache_file(weather_cache_path(config), weather_request(config))


def read_weather_cache_file(path: Path, request: dict) -> WeatherData:
    """Read and validate a cache for an explicit weather request."""
    try:
        with path.open(encoding="utf-8") as handle:
            return _decode_cache(json.load(handle), request)
    except (OSError, ValueError, TypeError) as exc:
        raise WeatherError(f"Weather cache cannot be read: {exc}") from exc


def _fetch_response(request: dict) -> dict:
    params = {
        name: value for name, value in request.items()
        if name not in {"provider", "endpoint", "elevation_policy", "cache_version"}
    }
    retries = Retry(
        total=2, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods={"GET"}, respect_retry_after_header=False,
    )
    try:
        with requests.Session() as session:
            session.mount("https://", HTTPAdapter(max_retries=retries))
            response = session.get(
                ENDPOINT, params=params, timeout=(10, 30),
                headers={"User-Agent": "DH-COMPASS/0.1 (non-commercial research)"},
            )
            response.raise_for_status()
            return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise WeatherError(
            "Local weather could not be downloaded from Open-Meteo. Check the internet "
            "connection and retry; a previously validated cache for this area/year can "
            "be used offline."
        ) from exc


def load_weather(config, *, force_refresh: bool = False) -> WeatherData:
    """Reuse matching validated weather or fetch and atomically cache it."""
    request = weather_request(config)
    path = weather_cache_path(config)
    if path.exists() and not force_refresh:
        try:
            result = read_weather_cache(config)
            LOGGER.info("Using cached local weather for %s, %s (%s)", request["latitude"],
                        request["longitude"], request["start_date"][:4])
            return result
        except WeatherError as exc:
            LOGGER.warning("Refreshing invalid weather cache: %s", exc)
    LOGGER.info("Loading local weather from Open-Meteo for %s, %s (%s)",
                request["latitude"], request["longitude"], request["start_date"][:4])
    response = _fetch_response(request)
    _validate_response(response, request)
    document = {
        "request": request,
        "response": response,
        "checksum": _digest(response),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    result = _decode_cache(document, request)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(document, handle, allow_nan=False)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return result
