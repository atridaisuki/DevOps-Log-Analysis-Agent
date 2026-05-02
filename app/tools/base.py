"""Base class and utilities for agent tools."""

from __future__ import annotations

from typing import Any, TypedDict


class ToolResult(TypedDict):
    success: bool
    data: Any
    error: str | None
