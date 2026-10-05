import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def _to_native_types(obj: object) -> object:
    """Convert numpy types and other non-JSON-serializable types to native Python types."""
    import numpy as np

    if isinstance(obj, dict):
        return {k: _to_native_types(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_to_native_types(item) for item in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj


class PerformanceTracker:
    def __init__(self) -> None:
        self.metrics: dict[str, list[float]] = {}
        self.optimization_metrics: dict[str, object] = {}

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        """Context manager to measure execution time of a block."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            if name not in self.metrics:
                self.metrics[name] = []
            self.metrics[name].append(duration)

    def get_stats(self) -> dict[str, dict[str, float]]:
        """Return statistics for all measured metrics."""
        stats = {}
        for name, values in self.metrics.items():
            stats[name] = {
                "count": len(values),
                "total_time": sum(values),
                "avg_time": sum(values) / len(values) if values else 0,
                "min_time": min(values) if values else 0,
                "max_time": max(values) if values else 0,
            }
        return stats

    def reset(self) -> None:
        """Clear all metrics."""
        self.metrics = {}
        self.optimization_metrics = {}

    def add_optimization_metric(self, key: str, value: object) -> None:
        """Add an optimization metric."""
        self.optimization_metrics[key] = value

    def save_to_json(self, filepath: str | Path) -> None:
        """Save metrics to a JSON file."""
        # Combine timing stats and optimization metrics
        # Convert numpy types to native Python types for JSON serialization
        output = {
            "timing_stats": _to_native_types(self.get_stats()),
            "optimization_metrics": _to_native_types(self.optimization_metrics),
        }
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with filepath.open("w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
