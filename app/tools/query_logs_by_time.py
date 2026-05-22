"""query_logs_by_time — retrieve log entries within a specific time window."""

from __future__ import annotations

import re
from pathlib import Path

from langchain_core.tools import tool

_TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} (\d{2}:\d{2}:\d{2})")


def _parse_time_to_seconds(t: str) -> int:
    parts = t.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = int(parts[2]) if len(parts) > 2 else 0
    return h * 3600 + m * 60 + s


@tool
def query_logs_by_time(
    scenario_path: str,
    service: str,
    start_time: str,
    end_time: str,
    severity: str = "",
    max_lines: int = 50,
) -> dict:
    """Query log entries within a specific time range for a service.

    Use this to correlate events across services by narrowing down to
    the same time window. First identify the anomaly window from metrics
    or one service's errors, then check other services in that window.

    Args:
        scenario_path: Path to the scenario directory.
        service: Service name (e.g., "api-gateway", "user-service").
        start_time: Start of time window, format "HH:MM" or "HH:MM:SS".
        end_time: End of time window, format "HH:MM" or "HH:MM:SS".
        severity: Optional filter: ERROR, WARN, INFO. Empty means all.
        max_lines: Maximum lines to return (default 50).

    Returns:
        dict with 'success', 'data' containing matched lines and stats.
    """
    logs_dir = Path(scenario_path) / "logs"
    log_file = logs_dir / f"{service}.log"

    if not log_file.exists():
        candidates = list(logs_dir.glob(f"{service}*.log"))
        if candidates:
            log_file = candidates[0]
        else:
            return {
                "success": False,
                "data": {},
                "error": f"No log file found for service: {service}",
            }

    start_secs = _parse_time_to_seconds(start_time)
    end_secs = _parse_time_to_seconds(end_time)
    severity_upper = severity.upper()

    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()

    matched = []
    total_in_range = 0
    severity_counts: dict[str, int] = {}

    for line in lines:
        m = _TS_PATTERN.match(line)
        if not m:
            continue
        line_secs = _parse_time_to_seconds(m.group(1))
        if line_secs < start_secs or line_secs > end_secs:
            continue

        total_in_range += 1

        level = ""
        parts = line.split(None, 3)
        if len(parts) >= 3:
            level = parts[2]
        severity_counts[level] = severity_counts.get(level, 0) + 1

        if severity_upper and level.upper() != severity_upper:
            continue

        if len(matched) < max_lines:
            matched.append(line.strip())

    return {
        "success": True,
        "data": {
            "service": service,
            "time_range": f"{start_time} - {end_time}",
            "total_lines_in_range": total_in_range,
            "severity_breakdown": severity_counts,
            "returned_lines": len(matched),
            "truncated": total_in_range > len(matched) if not severity_upper else False,
            "lines": matched,
        },
        "error": None,
    }
