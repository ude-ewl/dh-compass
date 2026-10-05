"""Versioned HTTP route modules."""

from .area import router as area_router
from .calculations import router as calculations_router
from .comparisons import router as comparisons_router
from .datasets import router as datasets_router
from .exports import router as exports_router
from .health import router as health_router
from .previews import router as previews_router
from .projects import router as projects_router
from .results import router as results_router
from .runs import router as runs_router

__all__ = [
    "area_router",
    "calculations_router",
    "comparisons_router",
    "datasets_router",
    "exports_router",
    "health_router",
    "previews_router",
    "projects_router",
    "results_router",
    "runs_router",
]
