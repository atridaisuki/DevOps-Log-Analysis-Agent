"""list_services — query service topology and dependencies."""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import tool


@tool
def list_services(
    scenario_path: str,
    service_name: str = "",
) -> dict:
    """List services in the system and their dependencies.

    Args:
        scenario_path: Path to the scenario directory.
        service_name: If provided, return details for this service only.
            If empty, return the full topology.

    Returns:
        dict with 'success', 'data' (topology info), and 'error'.
    """
    topo_file = Path(scenario_path) / "topology.json"
    if not topo_file.exists():
        return {"success": False, "data": {}, "error": "topology.json not found"}

    topology = json.loads(topo_file.read_text(encoding="utf-8"))
    services = topology.get("services", {})

    if service_name:
        if service_name not in services:
            return {
                "success": False,
                "data": {},
                "error": f"Service '{service_name}' not found. Available: {list(services.keys())}",
            }
        return {"success": True, "data": services[service_name], "error": None}

    # Return summary of all services
    summary = {}
    for name, info in services.items():
        summary[name] = {
            "port": info.get("port"),
            "depends_on": info.get("depends_on", []),
            "status": info.get("status", "unknown"),
        }

    return {"success": True, "data": summary, "error": None}
