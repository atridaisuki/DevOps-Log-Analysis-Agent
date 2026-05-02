"""Tests for the agent graph structure and routing logic — no LLM calls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import _should_continue, _should_use_tools
from app.agent.state import AgentState


def _make_state(**overrides) -> AgentState:
    """Create a minimal AgentState for testing."""
    base = {
        "messages": [],
        "user_goal": "test goal",
        "scenario_path": "/tmp/test",
        "current_plan": "",
        "hypotheses": [],
        "findings": [],
        "tool_call_history": [],
        "files_read": [],
        "iteration_count": 0,
        "max_iterations": 10,
        "status": "running",
    }
    base.update(overrides)
    return base


class TestRouting:
    def test_should_use_tools_with_tool_calls(self):
        """When the AI message has tool_calls, route to tool_executor."""
        ai_msg = AIMessage(content="", tool_calls=[
            {"id": "1", "name": "search_logs", "args": {"keyword": "error"}}
        ])
        state = _make_state(messages=[ai_msg])
        assert _should_use_tools(state) == "tool_executor"

    def test_should_use_tools_without_tool_calls(self):
        """When the AI message has no tool_calls, route to reporter."""
        ai_msg = AIMessage(content="Here is my analysis...")
        state = _make_state(messages=[ai_msg])
        assert _should_use_tools(state) == "reporter"

    def test_should_continue_when_running(self):
        state = _make_state(status="running")
        assert _should_continue(state) == "planner"

    def test_should_continue_when_completed(self):
        state = _make_state(status="completed")
        assert _should_continue(state) == "reporter"

    def test_should_continue_when_failed(self):
        state = _make_state(status="failed")
        assert _should_continue(state) == "reporter"


class TestCritic:
    def test_max_iterations_stops(self):
        """Critic should return completed when max iterations reached."""
        from app.agent.nodes import critic
        state = _make_state(iteration_count=10, max_iterations=10)
        result = critic(state)
        assert result["status"] == "completed"

    def test_consecutive_failures_stops(self):
        """Critic should return failed after 3 consecutive tool failures."""
        from app.agent.nodes import critic
        history = [
            {"tool_name": "t", "tool_input": {}, "tool_output": {}, "duration_ms": 0, "success": False},
            {"tool_name": "t", "tool_input": {}, "tool_output": {}, "duration_ms": 0, "success": False},
            {"tool_name": "t", "tool_input": {}, "tool_output": {}, "duration_ms": 0, "success": False},
        ]
        state = _make_state(
            iteration_count=5,
            max_iterations=10,
            tool_call_history=history,
        )
        result = critic(state)
        assert result["status"] == "failed"

    def test_early_iteration_continues(self):
        """Critic should continue if iteration < 2 (too early to judge)."""
        from app.agent.nodes import critic
        state = _make_state(iteration_count=1, max_iterations=10)
        result = critic(state)
        assert result["status"] == "running"
