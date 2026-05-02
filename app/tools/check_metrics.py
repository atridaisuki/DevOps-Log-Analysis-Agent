"""check_metrics — query service metrics (CPU, memory, latency, error rate)."""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import tool


@tool
def check_metrics(
    scenario_path: str,
    service_name: str,
    metric_type: str = "",
) -> dict:
    """Check metrics for a service.

    Args:
        scenario_path: Path to the scenario directory.
        service_name: Name of the service to check.
        metric_type: Specific metric to query (cpu, memory, latency, error_rate,
            connections). Empty means return all available metrics.

    Returns:
        dict with 'success', 'data' (metric values), and 'error'.
    """
    metrics_dir = Path(scenario_path) / "metrics"
    metrics_file = metrics_dir / f"{service_name}.json"

    if not metrics_file.exists():
        available = [f.stem for f in metrics_dir.glob("*.json")] if metrics_dir.exists() else []
        return {
            "success": False,
            "data": {},
            "error": f"No metrics for '{service_name}'. Available: {available}",
        }

    metrics = json.loads(metrics_file.read_text(encoding="utf-8"))

    if metric_type:
        if metric_type not in metrics:
            return {
                "success": False,
                "data": {},
                "error": f"Metric '{metric_type}' not found. Available: {list(metrics.keys())}",
            }
        return {"success": True, "data": {metric_type: metrics[metric_type]}, "error": None}

    return {"success": True, "data": metrics, "error": None}
