"""Public optimization contracts and workflow entry points."""

from .context import (
    ClusteringOptions,
    ContextDemandData,
    ContextMarketData,
    ContextTechnologyPortfolio,
    NetworkInputs,
    OptimizationContext,
    OptimizationResult,
    RuntimeServices,
    build_optimization_context,
)
from .model_inputs import (
    DemandTimeSeries,
    EconomicInputs,
    MarketTimeSeries,
    ModelInputs,
    ModelOptions,
    OptimizationContextLike,
    ResourceLimits,
    TechnologyPortfolio,
    build_model_inputs,
)
from .model_runner import ModelRun, ModelRunner, ModelRunTiming
from .orchestration import HeatGridOptimizer
from .result_extraction import (
    EnergyFlows,
    ModelSolution,
    StorageResult,
    TechnologyResult,
    extract_model_solution,
)
from .run_state import IterationRecord, OptimizationRunState

__all__ = [
    "ClusteringOptions",
    "ContextDemandData",
    "ContextMarketData",
    "ContextTechnologyPortfolio",
    "DemandTimeSeries",
    "EconomicInputs",
    "EnergyFlows",
    "HeatGridOptimizer",
    "IterationRecord",
    "MarketTimeSeries",
    "ModelInputs",
    "ModelOptions",
    "ModelRun",
    "ModelRunner",
    "ModelRunTiming",
    "ModelSolution",
    "NetworkInputs",
    "OptimizationContext",
    "OptimizationContextLike",
    "OptimizationResult",
    "OptimizationRunState",
    "ResourceLimits",
    "RuntimeServices",
    "StorageResult",
    "TechnologyPortfolio",
    "TechnologyResult",
    "build_model_inputs",
    "build_optimization_context",
    "extract_model_solution",
]
