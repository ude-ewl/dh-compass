"""Project and scenario persistence endpoints."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.engine import Engine

from ..persistence.migrations import run_migrations
from ..persistence.repositories import (
    UNSET,
    AuditRepository,
    MetadataNotFound,
    ProjectRepository,
    RevisionConflict,
    RunRepository,
    ScenarioRepository,
)
from ..schemas import (
    ApiError,
    ConfigurationSchemaResponse,
    ConfigurationValidationResponse,
    InvalidationEffects,
    Page,
    Pagination,
    ProjectCreate,
    ProjectDetail,
    ProjectListResponse,
    ProjectSummary,
    ProjectUpdate,
    RunHistory,
    RunHistoryListResponse,
    ScenarioConfigMutationResponse,
    ScenarioConfigResponse,
    ScenarioConfigUpdate,
    ScenarioCreate,
    ScenarioDetail,
    ScenarioDuplicate,
    ScenarioListResponse,
    ScenarioRevision,
    ScenarioSummary,
    ScenarioUpdate,
    TomlImport,
)
from ..services.configuration import ConfigurationAdapter

router = APIRouter(tags=["projects"])


def _engine(request: Request) -> Engine:
    engine = getattr(request.app.state, "metadata_engine", None)
    if isinstance(engine, Engine):
        return engine
    # Schema inspection tools and small unit fixtures may call a route without
    # entering TestClient's lifespan.  Keep that case deterministic while the
    # normal application path still migrates once at startup.
    from ..persistence.database import create_metadata_engine

    engine = create_metadata_engine(request.app.state.settings)
    run_migrations(engine)
    request.app.state.metadata_engine = engine
    return engine


def _adapter(request: Request) -> ConfigurationAdapter:
    adapter = getattr(request.app.state, "configuration_adapter", None)
    if isinstance(adapter, ConfigurationAdapter):
        return adapter
    adapter = ConfigurationAdapter(request.app.state.settings.project_root)
    request.app.state.configuration_adapter = adapter
    return adapter


def _projects(request: Request) -> ProjectRepository:
    return ProjectRepository(_engine(request))


def _scenarios(request: Request) -> ScenarioRepository:
    return ScenarioRepository(_engine(request), _adapter(request))


def _runs(request: Request) -> RunRepository:
    return RunRepository(_engine(request))


def _not_found(kind: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "NOT_FOUND", "message": f"{kind} was not found."},
    )


def _conflict(exc: RevisionConflict) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "SCENARIO_REVISION_CONFLICT",
            "message": str(exc),
            "details": {
                "scenario_id": exc.scenario_id,
                "expected_revision_id": exc.expected_revision_id,
                "current_revision_id": exc.current_revision_id,
                "current_document": exc.current_document,
            },
        },
    )


def _configuration_error(
    exc: Exception,
    adapter: ConfigurationAdapter | None = None,
) -> HTTPException:
    # This helper keeps error code/message consistent for import and config
    # routes.  The normalized application handler adds the request ID.
    field_errors = (
        [item.model_dump(mode="json") for item in adapter.field_errors(exc)]
        if adapter is not None
        else []
    )
    return HTTPException(
        status_code=422,
        detail={
            "code": "SCENARIO_VALIDATION_FAILED",
            "message": "The scenario configuration is invalid.",
            "field_errors": field_errors,
            "details": {"error": str(exc)},
        },
    )


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return (cleaned or "scenario")[:120] + ".toml"


def _page(items: list[Any], page: int, page_size: int) -> Page[Any]:
    total = len(items)
    start = (page - 1) * page_size
    return Page(
        items=items[start : start + page_size],
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total=total,
            has_next=start + page_size < total,
            has_previous=page > 1 and start < total,
        ),
    )


def _project_detail(request: Request, project_id: str) -> ProjectDetail:
    project = _projects(request).get(project_id)
    scenarios = _scenarios(request).list_for_project(project_id)
    return ProjectDetail(
        **project,
        scenarios=[ScenarioSummary(**item) for item in scenarios],
    )


def _scenario_detail(request: Request, scenario_id: str) -> ScenarioDetail:
    return ScenarioDetail(**_scenarios(request).get(scenario_id))


@router.get(
    "/projects",
    response_model=ProjectListResponse,
    responses={400: {"model": ApiError}},
    summary="List planning projects",
)
async def list_projects(
    request: Request,
    include_archived: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ProjectListResponse:
    records = [ProjectSummary(**item) for item in _projects(request).list(include_archived=include_archived)]
    return _page(records, page, page_size)


@router.post(
    "/projects",
    response_model=ProjectSummary,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ApiError}},
    summary="Create a planning project",
)
async def create_project(request: Request, payload: ProjectCreate) -> ProjectSummary:
    result = ProjectSummary(**_projects(request).create(payload.name.strip(), payload.description))
    _audit(request, "project.created", "project", result.id, {})
    return result


@router.get(
    "/projects/{project_id}",
    response_model=ProjectDetail,
    responses={404: {"model": ApiError}},
    summary="Return one project and its scenarios",
)
async def get_project(request: Request, project_id: str) -> ProjectDetail:
    try:
        return _project_detail(request, project_id)
    except MetadataNotFound as exc:
        raise _not_found("Project") from exc


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectSummary,
    responses={404: {"model": ApiError}},
    summary="Rename or edit a planning project",
)
async def update_project(request: Request, project_id: str, payload: ProjectUpdate) -> ProjectSummary:
    try:
        fields = payload.model_fields_set
        result = ProjectSummary(
            **_projects(request).update(
                project_id,
                name=payload.name if "name" in fields else None,
                description=payload.description if "description" in fields else UNSET,
            )
        )
    except MetadataNotFound as exc:
        raise _not_found("Project") from exc
    _audit(request, "project.updated", "project", project_id, {})
    return result


@router.post(
    "/projects/{project_id}/archive",
    response_model=ProjectSummary,
    responses={404: {"model": ApiError}},
    summary="Archive a project",
)
async def archive_project(request: Request, project_id: str) -> ProjectSummary:
    try:
        result = ProjectSummary(**_projects(request).archive(project_id))
    except MetadataNotFound as exc:
        raise _not_found("Project") from exc
    _audit(request, "project.archived", "project", project_id, {})
    return result


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ApiError}},
    summary="Delete project metadata",
)
async def delete_project(request: Request, project_id: str) -> Response:
    try:
        _projects(request).delete(project_id)
    except MetadataNotFound as exc:
        raise _not_found("Project") from exc
    _audit(request, "project.deleted", "project", project_id, {})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/projects/{project_id}/scenarios",
    response_model=ScenarioListResponse,
    responses={404: {"model": ApiError}},
    summary="List scenarios in a project",
)
async def list_scenarios(
    request: Request,
    project_id: str,
    include_archived: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> ScenarioListResponse:
    try:
        _projects(request).get(project_id)
        records = [
            ScenarioSummary(**item)
            for item in _scenarios(request).list_for_project(
                project_id, include_archived=include_archived
            )
        ]
    except MetadataNotFound as exc:
        raise _not_found("Project") from exc
    return _page(records, page, page_size)


@router.post(
    "/projects/{project_id}/scenarios",
    response_model=ScenarioDetail,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
    summary="Create a scenario from defaults or a document",
)
async def create_scenario(
    request: Request,
    project_id: str,
    payload: ScenarioCreate,
) -> ScenarioDetail:
    scenarios = _scenarios(request)
    try:
        document = payload.document if payload.document is not None else payload.configuration
        if payload.source_scenario_id:
            source = scenarios.get(payload.source_scenario_id)
            if source["project_id"] != project_id:
                raise _not_found("Source scenario")
            document = source["revision"]["document"]
        if document is not None:
            # Validate before opening the persistence transaction so an invalid
            # import cannot create a partial scenario.
            _adapter(request).validate(document)
        result = scenarios.create(
            project_id,
            payload.name.strip(),
            payload.description,
            document=document,
        )
    except MetadataNotFound as exc:
        raise _not_found("Project or source scenario") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise _configuration_error(exc, _adapter(request)) from exc
    response = ScenarioDetail(**result)
    _audit(request, "scenario.created", "scenario", response.id, {"project_id": project_id})
    return response


@router.get(
    "/scenarios/import",
    include_in_schema=False,
)
async def import_scenario_get() -> None:
    # Keep the reserved resource name from being interpreted as an ID by tools
    # that probe the route table.  Imports use POST below.
    raise HTTPException(status_code=405, detail="Use POST to import a scenario.")


@router.post(
    "/scenarios/import",
    response_model=ScenarioDetail,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
    summary="Import a scenario from TOML",
)
async def import_scenario(request: Request, payload: TomlImport) -> ScenarioDetail:
    try:
        validated = _adapter(request).import_toml(payload.submitted_toml)
        name = payload.name or str(validated.document.get("scenario", {}).get("case", "Imported scenario"))
        result = _scenarios(request).create(
            payload.project_id,
            name,
            payload.description,
            document=validated.document,
        )
    except MetadataNotFound as exc:
        raise _not_found("Project") from exc
    except Exception as exc:
        raise _configuration_error(exc, _adapter(request)) from exc
    response = ScenarioDetail(**result)
    _audit(request, "scenario.imported", "scenario", response.id, {"project_id": payload.project_id})
    return response


@router.get(
    "/scenarios/{scenario_id}",
    response_model=ScenarioDetail,
    responses={404: {"model": ApiError}},
    summary="Return one scenario",
)
async def get_scenario(request: Request, scenario_id: str) -> ScenarioDetail:
    try:
        return _scenario_detail(request, scenario_id)
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc


@router.patch(
    "/scenarios/{scenario_id}",
    response_model=ScenarioDetail,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}},
    summary="Edit scenario metadata with optimistic concurrency",
)
async def update_scenario(
    request: Request,
    scenario_id: str,
    payload: ScenarioUpdate,
) -> ScenarioDetail:
    try:
        fields = payload.model_fields_set
        result = _scenarios(request).update_metadata(
            scenario_id,
            expected_revision_id=payload.expected_revision_id,
            name=(
                payload.name
                if "name" in fields and payload.name is not None
                else UNSET
            ),
            description=payload.description if "description" in fields else UNSET,
            archived=(
                payload.archived
                if "archived" in fields and payload.archived is not None
                else UNSET
            ),
        )
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc
    except RevisionConflict as exc:
        raise _conflict(exc) from exc
    response = ScenarioDetail(**result)
    _audit(request, "scenario.updated", "scenario", scenario_id, {})
    return response


@router.post(
    "/scenarios/{scenario_id}/duplicate",
    response_model=ScenarioDetail,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ApiError}},
    summary="Duplicate a scenario and its current revision",
)
async def duplicate_scenario(
    request: Request,
    scenario_id: str,
    payload: ScenarioDuplicate | None = None,
) -> ScenarioDetail:
    try:
        result = _scenarios(request).duplicate(
            scenario_id,
            name=payload.name if payload else None,
            description=payload.description if payload else None,
        )
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc
    response = ScenarioDetail(**result)
    _audit(request, "scenario.duplicated", "scenario", response.id, {"source_scenario_id": scenario_id})
    return response


@router.get(
    "/scenarios/{scenario_id}/config",
    response_model=ScenarioConfigResponse,
    responses={404: {"model": ApiError}},
    summary="Return the validated scenario configuration",
)
async def get_scenario_config(
    request: Request,
    scenario_id: str,
    format: str = Query(default="json", pattern="^(json|toml)$"),
):
    try:
        scenario = _scenarios(request).get(scenario_id)
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc
    revision = scenario["revision"]
    adapter = _adapter(request)
    if format == "toml":
        content = adapter.export_toml(revision["document"])
        return PlainTextResponse(
            content,
            media_type="application/toml",
            headers={"Content-Disposition": f'attachment; filename="{_safe_filename(scenario["name"])}"'},
        )
    merged_toml = adapter.merged_toml(revision["document"])
    parent_document = None
    parent_revision_id = revision.get("parent_revision_id")
    if parent_revision_id:
        try:
            parent_document = _scenarios(request).get_revision(
                scenario_id, str(parent_revision_id)
            )["document"]
        except MetadataNotFound:
            parent_document = None
    fields = adapter.metadata(
        document=revision["document"],
        parent_document=parent_document,
    )
    return ScenarioConfigResponse(
        scenario_id=scenario_id,
        revision_id=revision["id"],
        revision_number=revision["revision_number"],
        parent_revision_id=parent_revision_id,
        document=revision["document"],
        effective_document=revision["document"],
        merged_toml=merged_toml,
        changed_from_default=[
            str(field["key"]) for field in fields if field.get("changed_from_default")
        ],
        changed_from_parent=[
            str(field["key"]) for field in fields if field.get("changed_from_parent")
        ],
        created_at=revision["created_at"],
    )


@router.get(
    "/scenarios/{scenario_id}/config.toml",
    response_class=PlainTextResponse,
    responses={404: {"model": ApiError}},
    summary="Download a scenario configuration as TOML",
)
async def export_scenario_toml(request: Request, scenario_id: str) -> PlainTextResponse:
    try:
        scenario = _scenarios(request).get(scenario_id)
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc
    content = _adapter(request).export_toml(scenario["revision"]["document"])
    return PlainTextResponse(
        content,
        media_type="application/toml",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(scenario["name"])}"'},
    )


@router.put(
    "/scenarios/{scenario_id}/config",
    response_model=ScenarioConfigMutationResponse,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}, 422: {"model": ApiError}},
    summary="Validate and atomically save a scenario configuration revision",
)
async def update_scenario_config(
    request: Request,
    scenario_id: str,
    payload: ScenarioConfigUpdate,
) -> ScenarioConfigMutationResponse:
    adapter = _adapter(request)
    scenarios = _scenarios(request)
    try:
        current = scenarios.get(scenario_id)
        base_document = current["revision"]["document"]
        if payload.toml is not None:
            validated = adapter.import_toml(
                payload.toml,
                base_document=base_document,
            )
            submitted_document = validated.document
            replace = True
        else:
            submitted_document = payload.submitted_document
            replace = payload.replace
        result = scenarios.update_config(
            scenario_id,
            expected_revision_id=payload.expected_revision_id,
            document=submitted_document,
            replace=replace,
        )
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc
    except RevisionConflict as exc:
        raise _conflict(exc) from exc
    except Exception as exc:
        raise _configuration_error(exc, adapter) from exc
    # Keep the response useful for both the form editor and raw TOML editor.
    # The adapter's public metadata method is the canonical source for the
    # changed-from-default comparison; no partially validated document is ever
    # persisted on failure.
    parent_document = None
    parent_revision_id = result.revision.get("parent_revision_id")
    if parent_revision_id:
        try:
            parent_document = scenarios.get_revision(
                scenario_id, str(parent_revision_id)
            )["document"]
        except MetadataNotFound:
            parent_document = None
    fields = adapter.metadata(
        document=result.revision["document"],
        parent_document=parent_document,
    )
    changed_from_default = [
        str(field["key"]) for field in fields if field.get("changed_from_default")
    ]
    changed_from_parent = [
        str(field["key"]) for field in fields if field.get("changed_from_parent")
    ]
    response = ScenarioConfigMutationResponse(
        scenario=ScenarioDetail(**result.scenario),
        revision=ScenarioRevision(**result.revision),
        invalidation=InvalidationEffects(**result.invalidation.as_dict()),
        merged_toml=adapter.merged_toml(result.revision["document"]),
        changed_from_default=changed_from_default,
        changed_from_parent=changed_from_parent,
    )
    _audit(
        request,
        "scenario.configuration_updated",
        "scenario",
        scenario_id,
        {"revision_id": response.revision.id, "changed_paths": response.invalidation.changed_paths},
    )
    return response


@router.post(
    "/scenarios/{scenario_id}/validate",
    response_model=ConfigurationValidationResponse,
    responses={404: {"model": ApiError}},
    summary="Validate a scenario configuration without saving it",
)
async def validate_scenario_config(
    request: Request,
    scenario_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> ConfigurationValidationResponse:
    adapter = _adapter(request)
    scenarios = _scenarios(request)
    try:
        scenario = scenarios.get(scenario_id)
        base_document = scenario["revision"]["document"]
        raw_toml = (
            payload["toml"]
            if "toml" in payload
            else payload.get("content")
        )
        if raw_toml is not None:
            validated = adapter.import_toml(
                raw_toml,
                base_document=base_document,
            )
        else:
            candidate = (
                payload.get("document")
                if isinstance(payload.get("document"), Mapping)
                else payload
            )
            validated = adapter.validate(
                candidate,
                base_document=base_document,
                replace=bool(payload.get("replace", False)),
            )
        invalidation = adapter.change(base_document, validated.document)
        fields = adapter.metadata(document=validated.document, parent_document=base_document)
        changed_from_default = [
            str(field["key"]) for field in fields if field.get("changed_from_default")
        ]
        changed_from_parent = [
            str(field["key"]) for field in fields if field.get("changed_from_parent")
        ]
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc
    except Exception as exc:
        field_errors = [item.model_dump(mode="json") for item in adapter.field_errors(exc)]
        return ConfigurationValidationResponse(
            valid=False,
            field_errors=field_errors,
        )
    return ConfigurationValidationResponse(
        valid=True,
        document=validated.document,
        effective_document=validated.document,
        merged_toml=adapter.merged_toml(
            validated.document,
            base_document=adapter.defaults,
        ),
        changed_paths=list(invalidation.changed_paths),
        changed_from_default=changed_from_default,
        changed_from_parent=changed_from_parent,
        invalidation=InvalidationEffects(**invalidation.as_dict()),
    )


@router.get(
    "/configuration/schema",
    response_model=ConfigurationSchemaResponse,
    summary="Return configuration labels, constraints, and impact metadata",
)
async def configuration_schema(
    request: Request,
    scenario_id: str | None = Query(default=None),
) -> ConfigurationSchemaResponse:
    adapter = _adapter(request)
    if scenario_id is None:
        return ConfigurationSchemaResponse(version="1", fields=adapter.metadata())
    try:
        scenario = _scenarios(request).get(scenario_id)
        revision = scenario["revision"]
        parent_document = None
        parent_revision_id = revision.get("parent_revision_id")
        if parent_revision_id:
            parent_document = _scenarios(request).get_revision(
                scenario_id, str(parent_revision_id)
            )["document"]
        fields = adapter.metadata(
            document=revision["document"],
            parent_document=parent_document,
        )
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc
    return ConfigurationSchemaResponse(
        version="1",
        fields=fields,
        scenario_id=scenario_id,
        revision_id=revision["id"],
        parent_revision_id=parent_revision_id,
    )


@router.get(
    "/projects/{project_id}/runs",
    response_model=RunHistoryListResponse,
    responses={404: {"model": ApiError}},
    summary="List run history placeholders for a project",
)
async def project_runs(
    request: Request,
    project_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> RunHistoryListResponse:
    try:
        _projects(request).get(project_id)
        records = [RunHistory(**item) for item in _runs(request).list_for_project(project_id)]
    except MetadataNotFound as exc:
        raise _not_found("Project") from exc
    return _page(records, page, page_size)


@router.get(
    "/scenarios/{scenario_id}/runs",
    response_model=RunHistoryListResponse,
    responses={404: {"model": ApiError}},
    summary="List run history placeholders for a scenario",
)
async def scenario_runs(
    request: Request,
    scenario_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> RunHistoryListResponse:
    try:
        _scenarios(request).get(scenario_id)
        records = [RunHistory(**item) for item in _runs(request).list_for_scenario(scenario_id)]
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc
    return _page(records, page, page_size)


@router.get(
    "/scenarios/{scenario_id}/revisions",
    response_model=Page[ScenarioRevision],
    responses={404: {"model": ApiError}},
    summary="List immutable scenario revisions",
)
async def scenario_revisions(
    request: Request,
    scenario_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[ScenarioRevision]:
    try:
        records = [ScenarioRevision(**item) for item in _scenarios(request).revisions(scenario_id)]
    except MetadataNotFound as exc:
        raise _not_found("Scenario") from exc
    return _page(records, page, page_size)


def _audit(
    request: Request,
    action: str,
    resource_type: str,
    resource_id: str | None,
    data: Mapping[str, Any],
) -> None:
    try:
        AuditRepository(_engine(request)).append(
            action,
            resource_type,
            resource_id,
            data=data,
        )
    except Exception:
        return


__all__ = ["router"]
