"""MCP Server — exposes DevOps log analysis tools via Model Context Protocol.

Run:
    python -m app.mcp_server

Any MCP-compatible client (Claude Desktop, Cursor, etc.) can then connect
and use these tools to investigate fault scenarios.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from app.config import settings

mcp = FastMCP(
    "DevOps Log Agent",
    instructions=(
        "Tools for investigating DevOps fault scenarios. "
        "Each scenario is a directory under data/scenarios/ containing "
        "logs, configs, metrics, and topology. "
        "Start with list_scenarios to see available scenarios, "
        "then use list_services, search_logs, and read_file to investigate."
    ),
)


# ── helper ───────────────────────────────────────────────────────────

def _scenarios_dir() -> Path:
    return Path(settings.scenarios_dir)


# ── tools ────────────────────────────────────────────────────────────

@mcp.tool()
def list_scenarios() -> str:
    """List all available fault scenarios.

    Returns a JSON array of scenario names with their descriptions.
    """
    base = _scenarios_dir()
    if not base.exists():
        return json.dumps({"error": f"Scenarios dir not found: {base}"})

    scenarios = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        desc_file = d / "description.json"
        if desc_file.exists():
            desc = json.loads(desc_file.read_text(encoding="utf-8"))
            scenarios.append({
                "name": d.name,
                "title": desc.get("title", ""),
                "description": desc.get("description", ""),
            })
        else:
            scenarios.append({"name": d.name, "title": "", "description": ""})

    return json.dumps(scenarios, ensure_ascii=False, indent=2)


@mcp.tool()
def list_services(scenario: str, service_name: str = "") -> str:
    """List services and their dependencies in a fault scenario.

    Args:
        scenario: Scenario directory name (e.g. 'scenario_01_db_pool').
        service_name: Optional — return details for this service only.
    """
    topo_file = _scenarios_dir() / scenario / "topology.json"
    if not topo_file.exists():
        return json.dumps({"error": f"topology.json not found in {scenario}"})

    topology = json.loads(topo_file.read_text(encoding="utf-8"))
    services = topology.get("services", {})

    if service_name:
        if service_name not in services:
            return json.dumps({
                "error": f"Service '{service_name}' not found",
                "available": list(services.keys()),
            })
        return json.dumps(services[service_name], ensure_ascii=False, indent=2)

    summary = {}
    for name, info in services.items():
        summary[name] = {
            "port": info.get("port"),
            "depends_on": info.get("depends_on", []),
            "status": info.get("status", "unknown"),
        }
    return json.dumps(summary, ensure_ascii=False, indent=2)


@mcp.tool()
def search_logs(
    scenario: str,
    keyword: str,
    severity: str = "",
    service_name: str = "",
    max_results: int = 30,
) -> str:
    """Search log files in a scenario for matching entries.

    Args:
        scenario: Scenario directory name.
        keyword: Keyword to search for (case-insensitive).
        severity: Filter by level — ERROR, WARN, INFO, DEBUG. Empty = all.
        service_name: Filter by service. Empty = search all.
        max_results: Max matching lines to return.
    """
    logs_dir = _scenarios_dir() / scenario / "logs"
    if not logs_dir.exists():
        return json.dumps({"error": f"No logs directory in {scenario}"})

    if service_name:
        log_files = list(logs_dir.glob(f"{service_name}*.log"))
        if not log_files:
            return json.dumps({"error": f"No logs for service: {service_name}"})
    else:
        log_files = list(logs_dir.glob("*.log"))

    matches = []
    kw_lower = keyword.lower()
    sev_upper = severity.upper()

    for log_file in sorted(log_files):
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            if len(matches) >= max_results:
                break
            if kw_lower and kw_lower not in line.lower():
                continue
            if sev_upper and sev_upper not in line.upper():
                continue

            ctx_start = max(0, i - 1)
            ctx_end = min(len(lines), i + 2)
            matches.append({
                "file": log_file.name,
                "line": i + 1,
                "match": line.strip(),
                "context": [l.strip() for l in lines[ctx_start:ctx_end]],
            })

    return json.dumps({"count": len(matches), "matches": matches}, ensure_ascii=False, indent=2)


@mcp.tool()
def read_file(scenario: str, file_path: str) -> str:
    """Read a file from a scenario directory.

    Args:
        scenario: Scenario directory name.
        file_path: Relative path within the scenario (e.g. 'configs/db.yaml').
    """
    base = (_scenarios_dir() / scenario).resolve()
    target = (base / file_path).resolve()

    if not str(target).startswith(str(base)):
        return json.dumps({"error": "Access denied: path outside scenario directory"})
    if not target.exists():
        return json.dumps({"error": f"File not found: {file_path}"})
    if not target.is_file():
        return json.dumps({"error": f"Not a file: {file_path}"})

    content = target.read_text(encoding="utf-8", errors="replace")
    # Truncate very large files
    if len(content) > 10000:
        content = content[:10000] + "\n... [truncated]"

    return content


@mcp.tool()
def check_metrics(scenario: str, service_name: str, metric_type: str = "") -> str:
    """Check metrics (CPU, memory, latency, error_rate) for a service.

    Args:
        scenario: Scenario directory name.
        service_name: Service to check.
        metric_type: Specific metric to query. Empty = return all.
    """
    metrics_file = _scenarios_dir() / scenario / "metrics" / f"{service_name}.json"
    if not metrics_file.exists():
        metrics_dir = _scenarios_dir() / scenario / "metrics"
        available = [f.stem for f in metrics_dir.glob("*.json")] if metrics_dir.exists() else []
        return json.dumps({"error": f"No metrics for '{service_name}'", "available": available})

    metrics = json.loads(metrics_file.read_text(encoding="utf-8"))

    if metric_type:
        if metric_type not in metrics:
            return json.dumps({"error": f"Metric '{metric_type}' not found", "available": list(metrics.keys())})
        return json.dumps({metric_type: metrics[metric_type]}, ensure_ascii=False, indent=2)

    return json.dumps(metrics, ensure_ascii=False, indent=2)


# ── entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
