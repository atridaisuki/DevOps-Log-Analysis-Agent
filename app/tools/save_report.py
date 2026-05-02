"""save_report — save a structured incident analysis report."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.tools import tool

from app.config import settings


@tool
def save_report(
    title: str,
    root_cause: str,
    evidence: list[str],
    suggestions: list[str],
    session_id: str = "default",
) -> dict:
    """Save a structured incident analysis report.

    Args:
        title: Report title summarizing the incident.
        root_cause: Identified root cause.
        evidence: List of evidence supporting the root cause.
        suggestions: List of fix / mitigation suggestions.
        session_id: Session identifier for file naming.

    Returns:
        dict with 'success', 'data' (saved file path), and 'error'.
    """
    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{session_id}_{timestamp}.json"
    filepath = reports_dir / filename

    report = {
        "title": title,
        "root_cause": root_cause,
        "evidence": evidence,
        "suggestions": suggestions,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
    }

    filepath.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "success": True,
        "data": {"file": str(filepath), "report": report},
        "error": None,
    }
