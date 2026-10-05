"""Provider provenance at the reporting boundary; no license grant for user data."""

from collections.abc import Mapping

OSM_PROVENANCE = {
    "source": "OpenStreetMap",
    "attribution": "© OpenStreetMap contributors",
    "source_url": "https://www.openstreetmap.org/copyright",
    "database_license": "ODbL-1.0",
    "license_url": "https://opendatacommons.org/licenses/odbl/1-0/",
    "scope": "OpenStreetMap-derived network geometry; demand, resource and model attributes retain separate source terms.",
    "export_review": "Review ODbL database obligations before redistributing derived networks.",
}


def with_map_provenance(value: object) -> object:
    """Copy JSON data, attaching provenance to embedded map collections."""
    if isinstance(value, Mapping):
        result = {key: with_map_provenance(item) for key, item in value.items()}
        if result.get("type") == "FeatureCollection":
            result.setdefault("source_provenance", dict(OSM_PROVENANCE))
        return result
    if isinstance(value, list):
        return [with_map_provenance(item) for item in value]
    return value
