"""Transport schemas for the redesign's one-command calculation contract."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, SkipValidation

from ..services.calculation_contract import (
    BBOX_COORDINATE_ORDER,
    DEFAULT_CONFIGURATION_VERSION,
)
from .base import APIModel

CalculationStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class CalculationCreate(APIModel):
    """Input accepted by ``POST /api/v1/calculations``.

    Semantic coverage and area limits are intentionally checked by the
    calculation contract service so the API can return stable issue codes.
    """

    # Preserve the raw JSON values for the calculation contract service.  It
    # owns every bbox validation error code, including non-numeric values;
    # Pydantic's normal float coercion would turn numeric strings into valid
    # input and bypass that stable API boundary.
    bbox: Annotated[list[float], SkipValidation] = Field(
        description=(
            "WGS84 coordinates in west, south, east, north order. "
            f"Order: {', '.join(BBOX_COORDINATE_ORDER)}."
        ),
    )


class CalculationAccepted(APIModel):
    """Stable response shape returned after a calculation is accepted."""

    run_id: str
    status: CalculationStatus
    status_url: str
    bbox: list[float] = Field(min_length=4, max_length=4)
    configuration_version: str = DEFAULT_CONFIGURATION_VERSION
    submitted_at: datetime | None = None
    idempotency_replayed: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class CalculationCommandContract(APIModel):
    """The command shape and retry semantics exposed to clients."""

    method: Literal["POST"]
    path: str
    body: dict[str, list[str]]
    idempotency_header: str
    idempotency: dict[str, str]


class CalculationBboxContract(APIModel):
    """Server-owned spatial coordinate and coverage limits."""

    crs: str
    coordinate_order: list[str] = Field(min_length=4, max_length=4)
    coverage_bbox: list[float] = Field(min_length=4, max_length=4)
    min_area_km2: float
    max_area_km2: float
    area_calculation: str


class CalculationDefaultsContract(APIModel):
    """Defaults that cannot be silently changed by the frontend."""

    configuration_version: str
    source: str
    frontend_may_not_override: bool


class CalculationAcceptedContract(APIModel):
    """Response payload promised after a command is accepted."""

    run_id: str
    status: Literal["queued"]
    status_url: str
    bbox: list[str] = Field(min_length=4, max_length=4)
    configuration_version: str


class CalculationLifecycleContract(APIModel):
    """Statuses and the stable accepted-response shape."""

    statuses: list[CalculationStatus]
    terminal_statuses: list[CalculationStatus]
    response: CalculationAcceptedContract


class CalculationContractResponse(APIModel):
    """Machine-readable limits and lifecycle semantics for frontend clients."""

    contract_version: str
    command: CalculationCommandContract
    bbox: CalculationBboxContract
    defaults: CalculationDefaultsContract
    lifecycle: CalculationLifecycleContract


__all__ = [
    "CalculationAccepted",
    "CalculationAcceptedContract",
    "CalculationBboxContract",
    "CalculationCommandContract",
    "CalculationContractResponse",
    "CalculationCreate",
    "CalculationDefaultsContract",
    "CalculationLifecycleContract",
    "CalculationStatus",
]
