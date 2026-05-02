"""Tests for the 5 agent tools — no LLM needed, pure file operations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tools.search_logs import search_logs
from app.tools.read_file import read_file
from app.tools.list_services import list_services
from app.tools.check_metrics import check_metrics

# Use scenario_01 as test fixture — it's the simplest and most stable
SCENARIO = str(Path(__file__).parent.parent / "data" / "scenarios" / "scenario_01_db_pool")


class TestSearchLogs:
    def test_keyword_match(self):
        result = search_logs.invoke({
            "scenario_path": SCENARIO,
            "keyword": "ERROR",
            "max_results": 5,
        })
        assert result["success"] is True
        assert len(result["data"]) > 0
        assert all("ERROR" in m["match"].upper() for m in result["data"])

    def test_severity_filter(self):
        result = search_logs.invoke({
            "scenario_path": SCENARIO,
            "keyword": "timeout",
            "severity": "ERROR",
            "max_results": 10,
        })
        assert result["success"] is True
        # All matches should contain ERROR
        for m in result["data"]:
            assert "ERROR" in m["match"].upper()

    def test_nonexistent_service(self):
        result = search_logs.invoke({
            "scenario_path": SCENARIO,
            "keyword": "error",
            "service_name": "nonexistent-service",
        })
        assert result["success"] is False

    def test_nonexistent_scenario(self):
        result = search_logs.invoke({
            "scenario_path": "/tmp/does_not_exist",
            "keyword": "error",
        })
        assert result["success"] is False

    def test_max_results_limit(self):
        result = search_logs.invoke({
            "scenario_path": SCENARIO,
            "keyword": "",  # match everything
            "max_results": 3,
        })
        assert result["success"] is True
        assert len(result["data"]) <= 3


class TestReadFile:
    def test_read_topology(self):
        result = read_file.invoke({
            "scenario_path": SCENARIO,
            "file_path": "topology.json",
        })
        assert result["success"] is True
        assert "content" in result["data"]

    def test_file_not_found(self):
        result = read_file.invoke({
            "scenario_path": SCENARIO,
            "file_path": "nonexistent.txt",
        })
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_path_traversal_blocked(self):
        result = read_file.invoke({
            "scenario_path": SCENARIO,
            "file_path": "../../pyproject.toml",
        })
        assert result["success"] is False
        assert "denied" in result["error"].lower() or "outside" in result["error"].lower()

    def test_line_range(self):
        result = read_file.invoke({
            "scenario_path": SCENARIO,
            "file_path": "topology.json",
            "start_line": 1,
            "end_line": 3,
        })
        assert result["success"] is True
        assert result["data"]["showing"].startswith("1-")


class TestListServices:
    def test_list_all(self):
        result = list_services.invoke({
            "scenario_path": SCENARIO,
        })
        assert result["success"] is True
        assert isinstance(result["data"], dict)
        assert len(result["data"]) > 0

    def test_specific_service(self):
        # First get all services to find a valid name
        all_result = list_services.invoke({"scenario_path": SCENARIO})
        service_name = list(all_result["data"].keys())[0]

        result = list_services.invoke({
            "scenario_path": SCENARIO,
            "service_name": service_name,
        })
        assert result["success"] is True

    def test_nonexistent_service(self):
        result = list_services.invoke({
            "scenario_path": SCENARIO,
            "service_name": "fake-service",
        })
        assert result["success"] is False


class TestCheckMetrics:
    def test_check_metrics(self):
        # Use a service that has metrics files in scenario_01
        result = check_metrics.invoke({
            "scenario_path": SCENARIO,
            "service_name": "user-service",
        })
        assert result["success"] is True
        assert isinstance(result["data"], dict)

    def test_nonexistent_service(self):
        result = check_metrics.invoke({
            "scenario_path": SCENARIO,
            "service_name": "fake-service",
        })
        assert result["success"] is False
