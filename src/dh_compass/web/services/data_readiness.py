"""Validation of the datasets needed by preprocessing.

The validators are deliberately conservative: they inspect metadata and small
schema samples, but never download data or execute a model.  A cache refresh is
only delegated to an explicitly injected provider.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Any, Callable

from shapely.geometry import box

from dh_compass.demand.weather import (
    read_weather_cache_file,
    weather_cache_path,
    weather_request,
)
from dh_compass.preprocessing.street_network import street_network_cache_path

from ..persistence.repositories import DatasetStateRepository, PreviewRepository
from ..schemas.base import ValidationIssue
from ..schemas.datasets import DatasetAction, DatasetDescriptor
from .configuration import ConfigurationAdapter


class DatasetValidationError(ValueError):
    """Raised for an unknown dataset or an invalid refresh request."""


class CacheRefreshUnavailable(RuntimeError):
    """Raised when a permitted cache action has no configured provider."""


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    id: str
    label: str
    description: str
    path: Path | None
    required: bool
    format: str | None = None
    layer: str | None = None
    columns: tuple[str, ...] = ()
    kind: str = "file"
    refreshable: bool = False
    resource_name: str | None = None
    candidates: tuple[Path, ...] = ()
    weather_request: Mapping[str, Any] | None = None
    slp_profiles: tuple[tuple[str, str], ...] = ()


_RESOURCE_PATHS = {
    "industrial_excess_heat": ("industrial_heat_path", "Industrial excess heat"),
    "biomass": ("biomass_path", "Biomass potential"),
    "waste_to_energy": ("waste_to_energy_path", "Waste-to-energy potential"),
    "geothermal": ("hydrothermal_path", "Geothermal potential"),
    "river_heat_pump": ("rivers_lakes_path", "River and lake potential"),
    "wwtp_heat_pump": ("wwtp_path", "Wastewater treatment potential"),
}


class DataReadinessService:
    """Describe and validate all input datasets for one scenario."""

    def __init__(
        self,
        adapter: ConfigurationAdapter,
        state_repository: DatasetStateRepository | None = None,
        *,
        project_root: str | Path | None = None,
        refreshers: Mapping[str, Callable[..., Any]] | None = None,
    ):
        self.adapter = adapter
        self.state_repository = state_repository
        self.refreshers = refreshers
        self.project_root = Path(project_root or adapter.project_root).expanduser().resolve()

    def definitions(self, scenario: Mapping[str, Any]) -> list[DatasetDefinition]:
        document = scenario.get("revision", {}).get("document", {})
        config = self.adapter.to_app_config(document)
        enabled = set(config.scenario.enabled_resources)
        definitions = [
            DatasetDefinition(
                id="buildings",
                label="Building demand data",
                description="Heated building geometries and annual demand attributes.",
                path=config.paths.building_data,
                required=True,
                format="FileGDB/GeoPackage/GeoJSON",
                layer=config.scenario.building_layer,
                columns=tuple(config.scenario.building_columns),
                kind="geospatial",
            ),
            DatasetDefinition(
                id="street_network",
                label="Street network cache",
                description="A managed local street-network cache for the study area.",
                path=None,
                required=True,
                format="GraphML",
                kind="cache",
                refreshable=True,
                candidates=(street_network_cache_path(config),),
            ),
            DatasetDefinition(
                id="time_series",
                label="Demand time series",
                description="Reference calendar factors for space heating and hot water; weather is acquired separately.",
                path=config.paths.historical_timeseries,
                required=True,
                format="CSV" if config.paths.historical_timeseries.suffix.lower() == ".csv" else "Excel",
                columns=("Datum",),
                kind="tabular",
            ),
            DatasetDefinition(
                id="slp_parameters",
                label="Standard load profile parameters",
                description="Gas SLP parameters and weekday factors used to generate heat demand profiles.",
                path=config.paths.slp_parameters,
                required=True,
                format="JSON" if config.paths.slp_parameters.suffix.lower() == ".json" else "Excel",
                kind="slp",
                slp_profiles=tuple(dict.fromkeys((
                    (config.demand.slp_profile_type_building, config.demand.slp_temperature_zone),
                    (config.demand.slp_profile_type_subgraph, config.demand.slp_temperature_zone),
                ))),
            ),
            DatasetDefinition(
                id="weather",
                label="Weather time series",
                description="Temperature data used by demand and heat-pump calculations.",
                path=weather_cache_path(config),
                required=True,
                format="Open-Meteo JSON",
                kind="weather",
                refreshable=True,
                candidates=(weather_cache_path(config),),
                weather_request=weather_request(config),
            ),
        ]
        for resource_name, (field, label) in _RESOURCE_PATHS.items():
            path = getattr(config.resources, field)
            definitions.append(
                DatasetDefinition(
                    id=resource_name,
                    label=label,
                    description="Optional location-dependent resource potential.",
                    path=path,
                    required=resource_name in enabled,
                    format="GeoPackage",
                    kind="resource",
                    resource_name=resource_name,
                )
            )
        return definitions

    def validate(
        self,
        scenario: Mapping[str, Any],
        *,
        dataset_ids: Sequence[str] | None = None,
    ) -> list[DatasetDescriptor]:
        definitions = self.definitions(scenario)
        allowed = {definition.id for definition in definitions}
        requested = set(dataset_ids) if dataset_ids is not None else allowed
        unknown = requested - allowed
        if unknown:
            names = ", ".join(sorted(unknown))
            raise DatasetValidationError(f"Unknown dataset identifier(s): {names}")
        area_bbox = self._scenario_bbox(scenario)
        stored_states = (
            self.state_repository.list_for_scenario(str(scenario["id"]))
            if self.state_repository is not None
            else {}
        )
        result: list[DatasetDescriptor] = []
        for definition in definitions:
            if definition.id not in requested:
                continue
            previous_state = stored_states.get(definition.id)
            descriptor = self._validate_definition(definition, area_bbox, previous_state)
            result.append(descriptor)
            if self.state_repository is not None:
                metadata = {
                    **descriptor.metadata,
                    "path_display": descriptor.path_display,
                    "extent": descriptor.extent,
                    "issues": [issue.model_dump(mode="json") for issue in descriptor.issues],
                }
                previous_metadata = previous_state.get("metadata", {}) if previous_state else {}
                if (
                    previous_state
                    and previous_metadata.get("fingerprint")
                    and previous_metadata.get("fingerprint") != metadata.get("fingerprint")
                    and scenario.get("preview_id")
                ):
                    PreviewRepository(self.state_repository.engine).mark_stale(
                        str(scenario["preview_id"]),
                        f"Dataset {definition.label} changed since the preview was generated.",
                    )
                self.state_repository.set(
                    str(scenario["id"]),
                    definition.id,
                    status=descriptor.status,
                    metadata=metadata,
                )
        return result

    def validate_one(self, scenario: Mapping[str, Any], dataset_id: str) -> DatasetDescriptor:
        values = self.validate(scenario, dataset_ids=[dataset_id])
        if not values:  # pragma: no cover - guarded by validate
            raise DatasetValidationError(f"Unknown dataset identifier: {dataset_id}")
        return values[0]

    def readiness(
        self,
        scenario: Mapping[str, Any],
        *,
        dataset_ids: Sequence[str] | None = None,
    ) -> tuple[list[DatasetDescriptor], list[ValidationIssue], bool]:
        descriptors = self.validate(scenario, dataset_ids=dataset_ids)
        blocking: list[ValidationIssue] = []
        for descriptor in descriptors:
            if not descriptor.required or descriptor.status == "ready":
                continue
            blocking.extend(descriptor.issues or [
                ValidationIssue(
                    severity="error",
                    code="DATASET_NOT_READY",
                    path=descriptor.id,
                    message=f"{descriptor.label} is not ready.",
                    remediation="Resolve the dataset issue before creating a preview.",
                )
            ])
        return descriptors, blocking, not blocking

    def refresh(
        self,
        scenario: Mapping[str, Any],
        dataset_id: str,
        *,
        force: bool = False,
        provider: Callable[..., Any] | None = None,
    ) -> DatasetDescriptor:
        definition = next(
            (item for item in self.definitions(scenario) if item.id == dataset_id),
            None,
        )
        if definition is None:
            raise DatasetValidationError(f"Unknown dataset identifier: {dataset_id}")
        if not definition.refreshable:
            raise DatasetValidationError(
                f"Dataset {dataset_id} cannot be refreshed by the web application."
            )
        if provider is None:
            raise CacheRefreshUnavailable(
                f"No managed refresh provider is configured for dataset {dataset_id}."
            )
        if self.state_repository is not None:
            self.state_repository.set(
                str(scenario["id"]), dataset_id, status="downloading", metadata={}
            )
        try:
            provider(scenario=scenario, dataset=definition, force=force)
        except Exception as exc:
            if self.state_repository is not None:
                self.state_repository.set(
                    str(scenario["id"]),
                    dataset_id,
                    status="invalid",
                    metadata={"refresh_error": str(exc)},
                )
            raise
        if scenario.get("preview_id") and self.state_repository is not None:
            PreviewRepository(self.state_repository.engine).mark_stale(
                str(scenario["preview_id"]),
                f"Dataset {definition.label} was refreshed.",
            )
        if self.state_repository is not None:
            self.state_repository.set(str(scenario["id"]), dataset_id, status="missing", metadata={})
        return self.validate_one(scenario, dataset_id)

    def _validate_definition(
        self,
        definition: DatasetDefinition,
        area_bbox: list[float],
        stored_state: Mapping[str, Any] | None,
    ) -> DatasetDescriptor:
        checked_at = datetime.now(timezone.utc)
        issues: list[ValidationIssue] = []
        path = definition.path
        if path is None:
            for candidate in definition.candidates:
                if candidate.exists():
                    path = candidate
                    break
        if (
            stored_state
            and stored_state.get("status") == "downloading"
            and (path is None or not path.exists())
        ):
            issues.append(
                ValidationIssue(
                    severity="info",
                    code="DATASET_REFRESH_IN_PROGRESS",
                    path=definition.id,
                    message="A managed cache refresh is in progress.",
                    remediation="Wait for the refresh to finish, then validate again.",
                )
            )
            status = "downloading"
            return self._descriptor(definition, status, path, issues, checked_at)
        elif path is None or not path.exists():
            if definition.required:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="DATASET_MISSING",
                        path=definition.id,
                        message=f"{definition.label} could not be found.",
                        remediation=(
                            "Use the permitted refresh action or configure the managed dataset path."
                            if definition.refreshable
                            else "Provide the dataset through the configured data root."
                        ),
                        details={"path": self._display_path(path or (definition.candidates[0] if definition.candidates else None))},
                    )
                )
                status = "missing"
            else:
                issues.append(
                    ValidationIssue(
                        severity="info",
                        code="OPTIONAL_RESOURCE_UNAVAILABLE",
                        path=definition.id,
                        message=f"{definition.label} is not available; the workflow can continue without it.",
                        remediation="Enable and provide this resource only when it is needed.",
                    )
                )
                status = "unavailable"
            return self._descriptor(definition, status, path, issues, checked_at)

        if not os.access(path, os.R_OK):
            issues.append(
                ValidationIssue(
                    severity="error" if definition.required else "warning",
                    code="DATASET_NOT_READABLE",
                    path=definition.id,
                    message=f"{definition.label} exists but is not readable.",
                    remediation="Check permissions for the managed data root.",
                )
            )
            return self._descriptor(
                definition,
                "invalid" if definition.required else "unavailable",
                path,
                issues,
                checked_at,
            )

        metadata: dict[str, Any] = {}
        extent: list[float] | None = None
        crs: str | None = None
        try:
            if definition.kind == "geospatial":
                metadata, extent, crs = self._inspect_geospatial(definition, path, area_bbox)
                if extent is not None and not self._overlaps(extent, area_bbox):
                    issues.append(
                        ValidationIssue(
                            severity="error" if definition.required else "warning",
                            code="DATASET_OUTSIDE_STUDY_AREA",
                            path=definition.id,
                            message=f"{definition.label} does not overlap the selected study area.",
                            remediation="Select a covered area or provide a dataset with matching coverage.",
                            details={"dataset_extent": extent, "study_area": area_bbox},
                        )
                    )
            elif definition.kind == "tabular":
                self._inspect_tabular(path, metadata, definition.columns)
            elif definition.kind == "slp":
                self._inspect_slp_parameters(path, metadata, definition.slp_profiles)
            elif definition.kind == "weather":
                self._inspect_weather(path, metadata, definition.weather_request)
            elif definition.kind == "cache":
                self._inspect_cache(path, metadata)
            elif definition.kind == "resource":
                metadata, extent, crs = self._inspect_resource(path, area_bbox)
                if extent is not None and not self._overlaps(extent, area_bbox):
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="RESOURCE_OUTSIDE_STUDY_AREA",
                            path=definition.id,
                            message=f"{definition.label} does not cover the selected area.",
                            remediation="The resource will be treated as unavailable in this area.",
                            details={"dataset_extent": extent, "study_area": area_bbox},
                        )
                    )
        except Exception as exc:
            issues.append(
                ValidationIssue(
                    severity="error" if definition.required else "warning",
                    code="DATASET_SCHEMA_INVALID",
                    path=definition.id,
                    message=f"{definition.label} could not be validated: {exc}",
                    remediation="Check the file format, required fields, and CRS.",
                    details={"error_type": type(exc).__name__},
                )
            )

        has_error = any(issue.severity == "error" for issue in issues)
        status = "invalid" if has_error else "ready"
        return self._descriptor(
            definition,
            status,
            path,
            issues,
            checked_at,
            metadata=metadata,
            extent=extent,
            crs=crs,
        )

    def _descriptor(
        self,
        definition: DatasetDefinition,
        status: str,
        path: Path | None,
        issues: list[ValidationIssue],
        checked_at: datetime,
        *,
        metadata: Mapping[str, Any] | None = None,
        extent: list[float] | None = None,
        crs: str | None = None,
    ) -> DatasetDescriptor:
        actions = []
        if definition.refreshable:
            refresh_allowed = self.refreshers is None or definition.id in self.refreshers
            actions.append(
                DatasetAction(
                    action="refresh",
                    label="Refresh managed cache",
                    allowed=refresh_allowed,
                    reason=None if refresh_allowed else "No refresh provider is configured.",
                )
            )
            if not refresh_allowed:
                issues = [
                    issue.model_copy(
                        update={
                            "remediation": (
                                "Automatic refresh is not configured. Configure a managed "
                                "refresh provider or supply the cache manually."
                            )
                        }
                    )
                    if issue.code == "DATASET_MISSING"
                    else issue
                    for issue in issues
                ]
        descriptor_metadata = dict(metadata or {})
        if path is not None:
            try:
                stat = path.stat()
                descriptor_metadata["fingerprint"] = f"{stat.st_size}:{stat.st_mtime_ns}"
            except OSError:
                descriptor_metadata["fingerprint"] = None
        return DatasetDescriptor(
            id=definition.id,
            label=definition.label,
            description=definition.description,
            required=definition.required,
            status=status,  # type: ignore[arg-type]
            path_display=self._display_path(path),
            format=definition.format,
            layer=definition.layer,
            columns=list(definition.columns),
            crs=crs,
            extent=extent,
            metadata=descriptor_metadata,
            issues=issues,
            actions=actions,
            checked_at=checked_at,
        )

    def _inspect_geospatial(
        self,
        definition: DatasetDefinition,
        path: Path,
        area_bbox: list[float],
    ) -> tuple[dict[str, Any], list[float] | None, str | None]:
        # pyogrio's metadata path avoids reading millions of building features
        # merely to check fields, CRS, and coverage.  GeoPandas remains the
        # fallback for installations without pyogrio and tiny test fixtures.
        try:
            import pyogrio

            kwargs: dict[str, Any] = {}
            if definition.layer and path.suffix.lower() not in {".geojson", ".json"}:
                kwargs["layer"] = definition.layer
            info = pyogrio.read_info(path, force_feature_count=False, **kwargs)
            fields = {str(value) for value in info.get("fields", [])}
            geometry_name = info.get("geometry_name")
            if geometry_name:
                fields.add(str(geometry_name))
            if definition.id == "buildings":
                from dh_compass.preprocessing.buildings import building_column_sources

                sources = building_column_sources(definition.columns, fields, geometry_name)
                fields.update(sources)
                fields.update(column for column in definition.columns if column.lower() in {"shape", "geometry"})
            missing = [column for column in definition.columns if column not in fields]
            if missing:
                raise ValueError(f"missing required columns: {', '.join(missing)}")
            source_crs = info.get("crs")
            if not source_crs:
                raise ValueError("dataset CRS is missing")
            raw_bounds = info.get("total_bounds")
            extent = self._transform_bounds(raw_bounds, str(source_crs))
            if extent is None:
                raise ValueError("dataset has no spatial extent")
            return {
                "columns_available": sorted(fields),
                "layer": info.get("layer_name") or definition.layer,
                "feature_count": info.get("features"),
                "geometry_type": info.get("geometry_type"),
            }, extent, str(source_crs)
        except ImportError:
            import geopandas as gpd

            kwargs = {}
            if definition.layer and path.suffix.lower() not in {".geojson", ".json"}:
                kwargs["layer"] = definition.layer
            frame = gpd.read_file(path, rows=0, **kwargs)
            available_columns = {str(column) for column in frame.columns}
            missing = [column for column in definition.columns if column not in available_columns]
            if missing:
                raise ValueError(f"missing required columns: {', '.join(missing)}")
            if frame.crs is None:
                raise ValueError("dataset CRS is missing")
            bounds = frame.to_crs(4326).total_bounds
            extent = [float(value) for value in bounds]
            return {
                "columns_available": sorted(available_columns),
                "layer": definition.layer,
                "feature_count_sample": int(len(frame)),
            }, extent, str(frame.crs)

    @staticmethod
    def _inspect_tabular(
        path: Path,
        metadata: dict[str, Any],
        required_columns: Sequence[str] = (),
    ) -> None:
        suffix = path.suffix.lower()
        metadata["suffix"] = suffix
        if suffix in {".xlsx", ".xls", ".xlsm"}:
            import zipfile

            if suffix == ".xlsx" or suffix == ".xlsm":
                with zipfile.ZipFile(path) as archive:
                    if "xl/workbook.xml" not in archive.namelist():
                        raise ValueError("Excel workbook is missing workbook metadata")
            else:
                with path.open("rb") as handle:
                    if not handle.read(8):
                        raise ValueError("Excel file is empty")
            if required_columns:
                import pandas as pd

                columns = {str(column) for column in pd.read_excel(path, nrows=0).columns}
                missing = [column for column in required_columns if column not in columns]
                if missing:
                    raise ValueError(f"missing required columns: {', '.join(missing)}")
        elif suffix in {".csv", ".txt"}:
            import pandas as pd

            columns = {str(column) for column in pd.read_csv(path, nrows=0).columns}
            missing = [column for column in required_columns if column not in columns]
            if missing:
                raise ValueError(f"missing required columns: {', '.join(missing)}")
        else:
            with path.open("rb") as handle:
                handle.read(1)

    @staticmethod
    def _inspect_slp_parameters(path: Path, metadata: dict[str, Any], profiles=()) -> None:
        from dh_compass.demand.slp_inputs import read_slp_tables

        parameters, factors = read_slp_tables(path, profiles)
        metadata["sheets"] = ["Parameter", "Tagesfaktoren"]
        metadata["profile_count"] = len(parameters)
        metadata["category_count"] = len(factors)
        metadata["byte_size"] = path.stat().st_size

    @staticmethod
    def _inspect_weather(
        path: Path, metadata: dict[str, Any], request: Mapping[str, Any] | None = None
    ) -> None:
        if request is None:
            raise ValueError("weather request metadata is missing")
        weather = read_weather_cache_file(path, dict(request))
        metadata.update(weather.provenance)
        metadata["byte_size"] = path.stat().st_size
        metadata["suffix"] = path.suffix.lower()

    @staticmethod
    def _inspect_cache(path: Path, metadata: dict[str, Any]) -> None:
        if not path.is_file():
            raise ValueError("cache path is not a file")
        metadata["byte_size"] = path.stat().st_size
        metadata["cache_path"] = path.name
        suffix = path.suffix.lower()
        if suffix == ".json":
            with path.open("r", encoding="utf-8") as handle:
                json.load(handle)
        elif suffix == ".graphml":
            import networkx as nx

            nx.read_graphml(path)
        elif suffix in {".gpkg", ".geojson", ".json"}:
            import pyogrio

            pyogrio.read_info(path, force_feature_count=False)

    def _inspect_resource(
        self, path: Path, area_bbox: list[float]
    ) -> tuple[dict[str, Any], list[float] | None, str | None]:
        del area_bbox
        try:
            import pyogrio

            info = pyogrio.read_info(path, force_feature_count=False)
            source_crs = info.get("crs")
            if not source_crs:
                raise ValueError("resource CRS is missing")
            extent = self._transform_bounds(info.get("total_bounds"), str(source_crs))
            return {
                "feature_count": info.get("features"),
                "geometry_type": info.get("geometry_type"),
            }, extent, str(source_crs)
        except ImportError:
            import geopandas as gpd

            frame = gpd.read_file(path, rows=0)
            if frame.crs is None:
                raise ValueError("resource CRS is missing")
            normalized = frame.to_crs(4326)
            bounds = normalized.total_bounds
            extent = [float(value) for value in bounds]
            return {"feature_count_sample": int(len(frame))}, extent, str(frame.crs)

    @staticmethod
    def _transform_bounds(bounds: Any, source_crs: str) -> list[float] | None:
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
            return None
        try:
            values = [float(value) for value in bounds]
            if not all(isfinite(value) for value in values):
                return None
            if source_crs.upper() in {"EPSG:4326", "CRS84", "OGC:CRS84"}:
                return values
            from pyproj import Transformer

            transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
            # Projected rectangle edges become curves after reprojection.
            # Densify them so large extents (including overseas territories)
            # do not incorrectly exclude areas between the diagonal corners.
            extent = [
                float(value)
                for value in transformer.transform_bounds(*values, densify_pts=21)
            ]
            return extent if all(isfinite(value) for value in extent) else None
        except (TypeError, ValueError, ImportError):
            return None

    @staticmethod
    def _overlaps(left: Sequence[float], right: Sequence[float]) -> bool:
        try:
            return box(*left).intersects(box(*right))
        except (TypeError, ValueError):
            return False

    def _scenario_bbox(self, scenario: Mapping[str, Any]) -> list[float]:
        revision = scenario.get("revision")
        document = revision.get("document", {}) if isinstance(revision, Mapping) else {}
        section = document.get("scenario", {}) if isinstance(document, Mapping) else {}
        bbox = section.get("bbox") if isinstance(section, Mapping) else None
        if not isinstance(bbox, (list, tuple)):
            raise DatasetValidationError("Scenario does not contain a study-area bbox.")
        from .study_area import validate_bbox

        return validate_bbox(bbox)

    def _display_path(self, path: Path | None) -> str | None:
        if path is None:
            return None
        resolved = Path(path).expanduser().resolve()
        try:
            return resolved.relative_to(self.project_root).as_posix()
        except ValueError:
            return resolved.name


__all__ = [
    "CacheRefreshUnavailable",
    "DataReadinessService",
    "DatasetDefinition",
    "DatasetValidationError",
]
