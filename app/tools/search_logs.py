"""search_logs — search log files by keyword, severity, time range."""

from __future__ import annotations

import os
import re
from pathlib import Path

from langchain_core.tools import tool


@tool
def search_logs(
    scenario_path: str,
    keyword: str,
    severity: str = "",
    service_name: str = "",
    max_results: int = 30,
) -> dict:
    """Search log files in a scenario for matching entries.

    Args:
        scenario_path: Path to the scenario directory.
        keyword: Keyword to search for in log lines.
        severity: Filter by severity level (ERROR, WARN, INFO, DEBUG). Empty means all.
        service_name: Filter by service name. Empty means search all services.
        max_results: Maximum number of matching lines to return.

    Returns:
        dict with 'success', 'data' (list of matching log lines with context), and 'error'.
    """
    logs_dir = Path(scenario_path) / "logs"
    if not logs_dir.exists():
        return {"success": False, "data": [], "error": f"Logs directory not found: {logs_dir}"}

    # Determine which log files to search
    if service_name:
        log_files = list(logs_dir.glob(f"{service_name}*.log"))
        if not log_files:
            return {"success": False, "data": [], "error": f"No log files found for service: {service_name}"}
    else:
        log_files = list(logs_dir.glob("*.log"))

    matches: list[dict] = []
    keyword_lower = keyword.lower()
    severity_upper = severity.upper()

    for log_file in sorted(log_files):
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            if len(matches) >= max_results:
                break

            # Keyword filter
            if keyword_lower not in line.lower():
                continue

            # Severity filter
            if severity_upper and severity_upper not in line.upper():
                continue

            # Collect match with surrounding context (1 line before, 1 after)
            context_start = max(0, i - 1)
            context_end = min(len(lines), i + 2)
            context = lines[context_start:context_end]

            matches.append({
                "file": log_file.name,
                "line_number": i + 1,
                "match": line.strip(),
                "context": [l.strip() for l in context],
            })

    return {
        "success": True,
        "data": matches,
        "error": None,
    }
