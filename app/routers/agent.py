"""Agent API routes."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from app.agent.graph import build_graph
from app.agent.state import AgentState
from app.config import settings
from app.schemas import AnalyzeRequest, AnalyzeResponse, ToolTrace

router = APIRouter()

# Compile graph once at module level (includes MemorySaver checkpointer)
_graph = build_graph()


def _build_input_state(
    req: AnalyzeRequest, scenario_path: str
) -> tuple[dict, bool]:
    """Build the input state, checking for existing session."""
    session_id = req.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    existing_state = _graph.get_state(config)
    is_continuation = (
        existing_state.values.get("messages") is not None
        and len(existing_state.values.get("messages", [])) > 0
    )

    if is_continuation:
        input_state = {
            "messages": [HumanMessage(content=req.goal)],
            "status": "running",
            "iteration_count": 0,
            "max_iterations": req.max_iterations,
        }
    else:
        input_state = {
            "user_goal": req.goal,
            "scenario_path": scenario_path,
            "messages": [HumanMessage(content=req.goal)],
            "current_plan": "",
            "hypotheses": [],
            "findings": [],
            "tool_call_history": [],
            "files_read": [],
            "iteration_count": 0,
            "max_iterations": req.max_iterations,
            "status": "running",
        }

    return input_state, session_id, config


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """Run the agent synchronously and return the full result."""
    scenario_path = str(Path(settings.scenarios_dir) / req.scenario)
    if not Path(scenario_path).exists():
        raise HTTPException(404, f"Scenario not found: {req.scenario}")

    input_state, session_id, config = _build_input_state(req, scenario_path)

    start = time.perf_counter()
    result = _graph.invoke(input_state, config)

    # Handle human-in-the-loop interrupt:
    # The graph pauses before "reporter". If auto_approve is True,
    # we resume immediately. Otherwise, return a "paused" response
    # so the client can review findings before requesting the report.
    state_snapshot = _graph.get_state(config)
    if state_snapshot.next and "reporter" in state_snapshot.next:
        if req.auto_approve:
            # Auto-resume: continue past the interrupt
            result = _graph.invoke(None, config)
        else:
            # Return paused state — client must call POST /agent/resume
            total_ms = (time.perf_counter() - start) * 1000
            return AnalyzeResponse(
                session_id=session_id,
                status="paused_before_report",
                root_cause="",
                findings=state_snapshot.values.get("findings", []),
                suggestions=[],
                tool_trace=[
                    ToolTrace(**r)
                    for r in state_snapshot.values.get("tool_call_history", [])
                ],
                iterations=state_snapshot.values.get("iteration_count", 0),
                total_duration_ms=round(total_ms, 2),
            )

    total_ms = (time.perf_counter() - start) * 1000

    # Extract final report from last AI message
    final_report = ""
    for msg in reversed(result["messages"]):
        if hasattr(msg, "content") and msg.content and not hasattr(msg, "tool_call_id"):
            final_report = msg.content
            break

    tool_trace = [
        ToolTrace(
            tool_name=r["tool_name"],
            tool_input=r["tool_input"],
            tool_output=r["tool_output"],
            duration_ms=r["duration_ms"],
            success=r["success"],
        )
        for r in result.get("tool_call_history", [])
    ]

    return AnalyzeResponse(
        session_id=session_id,
        status=result.get("status", "completed"),
        root_cause=final_report,
        findings=result.get("findings", []),
        suggestions=[],
        tool_trace=tool_trace,
        iterations=result.get("iteration_count", 0),
        total_duration_ms=round(total_ms, 2),
    )


@router.post("/analyze/stream")
async def analyze_stream(req: AnalyzeRequest):
    """Stream the agent execution as Server-Sent Events.

    Each SSE event contains the node name and a summary of what happened.
    """
    scenario_path = str(Path(settings.scenarios_dir) / req.scenario)
    if not Path(scenario_path).exists():
        raise HTTPException(404, f"Scenario not found: {req.scenario}")

    input_state, session_id, config = _build_input_state(req, scenario_path)

    async def event_generator() -> AsyncGenerator[str, None]:
        # Send session info
        yield _sse_event("session", {"session_id": session_id})

        start = time.perf_counter()

        #只要invoke改stream就是sse了
        for event in _graph.stream(input_state, config, stream_mode="updates"):
            for node_name, updates in event.items():
                payload = {"node": node_name}

                # Extract useful info depending on node type
                if node_name == "planner":
                    msgs = updates.get("messages", [])
                    if msgs and isinstance(msgs[0], AIMessage):
                        ai_msg = msgs[0]
                        if ai_msg.tool_calls:
                            tools = [tc["name"] for tc in ai_msg.tool_calls]
                            payload["action"] = "tool_calls"
                            payload["tools"] = tools
                        else:
                            payload["action"] = "final_answer"
                            payload["preview"] = (ai_msg.content or "")[:200]
                    payload["iteration"] = updates.get("iteration_count")

                elif node_name == "tool_executor":
                    history = updates.get("tool_call_history", [])
                    payload["results"] = [
                        {
                            "tool": r["tool_name"],
                            "success": r["success"],
                            "duration_ms": r["duration_ms"],
                        }
                        for r in history
                    ]

                elif node_name == "critic":
                    payload["status"] = updates.get("status", "running")

                elif node_name == "reporter":
                    msgs = updates.get("messages", [])
                    if msgs:
                        payload["report_preview"] = (msgs[0].content or "")[:300]

                yield _sse_event("node", payload)

        total_ms = (time.perf_counter() - start) * 1000
        yield _sse_event("done", {"total_duration_ms": round(total_ms, 2)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class ResumeRequest(BaseModel):
    session_id: str = Field(..., description="Session ID of the paused analysis")


@router.post("/resume", response_model=AnalyzeResponse)
async def resume(req: ResumeRequest):
    """Resume a paused analysis (after human-in-the-loop review).

    Call this after receiving a 'paused_before_report' status to let
    the agent generate the final report.
    """
    config = {"configurable": {"thread_id": req.session_id}}

    state_snapshot = _graph.get_state(config)
    if not state_snapshot.next:
        raise HTTPException(400, "No paused session found for this session_id")

    start = time.perf_counter()
    result = _graph.invoke(None, config)
    total_ms = (time.perf_counter() - start) * 1000

    final_report = ""
    for msg in reversed(result["messages"]):
        if hasattr(msg, "content") and msg.content and not hasattr(msg, "tool_call_id"):
            final_report = msg.content
            break

    tool_trace = [
        ToolTrace(**r) for r in result.get("tool_call_history", [])
    ]

    return AnalyzeResponse(
        session_id=req.session_id,
        status=result.get("status", "completed"),
        root_cause=final_report,
        findings=result.get("findings", []),
        suggestions=[],
        tool_trace=tool_trace,
        iterations=result.get("iteration_count", 0),
        total_duration_ms=round(total_ms, 2),
    )
