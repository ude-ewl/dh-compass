"""JSON serialization and persistence for reporting results."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from ..optimization.context import OptimizationResult
from ..optimization.orchestration import HeatGridOptimizer
from .result_schema import assemble_full_results


def to_native(value: object) -> object:
    """Convert NumPy/Pandas values at the JSON serialization boundary."""

    if isinstance(value, Mapping):
        return {to_native(key): to_native(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return to_native(value.tolist())
    if isinstance(value, pd.DataFrame):
        return to_native(value.to_dict(orient="records"))
    if isinstance(value, pd.Series):
        return to_native(value.tolist())
    if isinstance(value, pd.Index):
        return to_native(value.tolist())
    if isinstance(value, (list, tuple, set)):
        return [to_native(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.datetime64):
        return None if np.isnat(value) else str(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if value is pd.NaT or value is pd.NA:
        return None
    return value


def build_full_results_json(
    optimizer: HeatGridOptimizer,
    optimization_results: Sequence[OptimizationResult],
    flh: float = 3000,
) -> dict[str, object]:
    """Assemble and normalize the full-results document."""

    return to_native(assemble_full_results(optimizer, optimization_results, flh=flh))


def save_full_results_json(data: Mapping[str, object], filepath: str | Path) -> None:
    """Serialize a full-results document to ``filepath``."""

    output_path = Path(filepath)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(to_native(data), handle, indent=2, ensure_ascii=False)


__all__ = [
    "build_full_results_json",
    "save_full_results_json",
    "to_native",
]
