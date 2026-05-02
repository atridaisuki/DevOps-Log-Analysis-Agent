"""read_file — read a file within the scenario directory."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool


@tool
def read_file(
    scenario_path: str,
    file_path: str,
    start_line: int = 1,
    end_line: int = 200,
) -> dict:
    """Read a file from the scenario directory.

    Args:
        scenario_path: Path to the scenario directory.
        file_path: Relative path within the scenario (e.g. 'configs/db-service.yaml').
        start_line: First line to read (1-indexed).
        end_line: Last line to read (inclusive). Max 200 lines per call.

    Returns:
        dict with 'success', 'data' (file content), and 'error'.
    """
    base = Path(scenario_path).resolve()
    target = (base / file_path).resolve()

    # Security: ensure target is inside scenario directory
    if not str(target).startswith(str(base)):
        return {"success": False, "data": "", "error": "Access denied: path is outside scenario directory"}

    if not target.exists():
        return {"success": False, "data": "", "error": f"File not found: {file_path}"}

    if not target.is_file():
        return {"success": False, "data": "", "error": f"Not a file: {file_path}"}

    # Clamp range
    end_line = min(end_line, start_line + 199)

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    selected = lines[start_line - 1 : end_line]

    # Add line numbers
    numbered = [f"{start_line + i:4d} | {line}" for i, line in enumerate(selected)]

    return {
        "success": True,
        "data": {
            "file": file_path,
            "total_lines": len(lines),
            "showing": f"{start_line}-{min(end_line, len(lines))}",
            "content": "\n".join(numbered),
        },
        "error": None,
    }
