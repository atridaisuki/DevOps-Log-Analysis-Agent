"""Agent graph nodes — planner, tool_executor, observer, critic, reporter."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.memory import maybe_compress_messages
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentState, ToolCallRecord
from app.config import settings
from app.tools import ALL_TOOLS

# Build a name→function lookup for tool execution
_TOOL_MAP = {t.name: t for t in ALL_TOOLS}


def _get_llm() -> ChatAnthropic:
    kwargs: dict = {
        "model": settings.anthropic_model,
        "api_key": settings.anthropic_api_key,
        "max_tokens": 4096,
    }
    if settings.anthropic_base_url:
        kwargs["base_url"] = settings.anthropic_base_url
    return ChatAnthropic(**kwargs)


# ── planner ──────────────────────────────────────────────────────────
def planner(state: AgentState) -> dict:
    """Call the LLM with the current conversation and available tools.

    The LLM decides whether to call a tool or produce a final answer.
    """
    llm = _get_llm().bind_tools(ALL_TOOLS)

    # First turn: inject the user goal as a HumanMessage
    messages = list(state["messages"])
    if not messages:
        messages = [HumanMessage(content=state["user_goal"])]

    # Compress older messages if context is getting too long
    messages = maybe_compress_messages(messages)

    # Tell the LLM which files have already been read
    files_read = state.get("files_read", [])
    if files_read:
        files_note = "\n\nFiles already read (do not re-read): " + ", ".join(files_read)
        sys_content = SYSTEM_PROMPT.format(scenario_path=state["scenario_path"]) + files_note
    else:
        sys_content = SYSTEM_PROMPT.format(scenario_path=state["scenario_path"])

    sys_msg = SystemMessage(content=sys_content)

    response = llm.invoke([sys_msg] + messages)

    # Log planner decision
    tool_names = [tc["name"] for tc in response.tool_calls] if response.tool_calls else []
    logger.info(
        "planner: iteration=%d, action=%s, tools=%s",
        state["iteration_count"] + 1,
        "tool_calls" if tool_names else "final_answer",
        tool_names or "none",
    )

    return {
        "messages": [response],
        "iteration_count": state["iteration_count"] + 1,
    }


# ── tool_executor ────────────────────────────────────────────────────

logger = logging.getLogger("agent")


def _execute_single_tool(tool_name: str, tool_input: dict, tool_fn) -> tuple[dict, bool, float]:
    """Execute one tool with retry logic. Returns (result, success, elapsed_ms)."""
    start = time.perf_counter()

    if tool_fn is None:
        result = {"success": False, "data": None, "error": f"Unknown tool: {tool_name}"}
        elapsed_ms = (time.perf_counter() - start) * 1000
        return result, False, round(elapsed_ms, 2)

    # Retry logic: up to 2 attempts on transient exceptions
    max_retries = 2
    for attempt in range(max_retries):
        try:
            result = tool_fn.invoke(tool_input)
            success = result.get("success", True) if isinstance(result, dict) else True
            # Don't retry logical errors (e.g. file not found)
            break
        except Exception as exc:
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue
            result = {"success": False, "data": None, "error": str(exc)}
            success = False

    elapsed_ms = (time.perf_counter() - start) * 1000
    return result, success, round(elapsed_ms, 2)


def  tool_executor(state: AgentState) -> dict:
    """Execute the tool calls requested by the planner.

    When multiple tools are requested, independent calls run in parallel
    using a thread pool. read_file deduplication is checked upfront.
    """
    last_message: AIMessage = state["messages"][-1]
    tool_calls = last_message.tool_calls

    new_files_read: list[str] = list(state.get("files_read", []))

    # Separate dedup-skipped calls from real calls
    skip_results: dict[str, tuple[dict, ToolCallRecord]] = {}  # tc_id -> (result, record)
    to_execute: list[tuple[str, dict, str, Any]] = []  # (tc_id, tool_input, tool_name, tool_fn)

    for tc in tool_calls:
        tool_name = tc["name"]
        tool_input = tc["args"]

        # Dedup: skip read_file if already read this exact file
        if tool_name == "read_file":
            file_key = tool_input.get("file_path", "")
            if file_key in new_files_read:
                result = {
                    "success": True,
                    "data": f"[Already read '{file_key}' — see previous results above]",
                    "error": None,
                }
                skip_results[tc["id"]] = (result, ToolCallRecord(
                    tool_name=tool_name, tool_input=tool_input,
                    tool_output=result, duration_ms=0.0, success=True,
                ))
                continue
            else:
                new_files_read.append(file_key)

        tool_fn = _TOOL_MAP.get(tool_name)
        to_execute.append((tc["id"], tool_input, tool_name, tool_fn))

    # Execute tools in parallel when there are multiple calls
    exec_results: dict[str, tuple[dict, bool, float, str, dict]] = {}

    if len(to_execute) == 1:
        # Single tool — no need for thread pool overhead
        tc_id, tool_input, tool_name, tool_fn = to_execute[0]
        result, success, elapsed = _execute_single_tool(tool_name, tool_input, tool_fn)
        exec_results[tc_id] = (result, success, elapsed, tool_name, tool_input)
    elif to_execute:
        with ThreadPoolExecutor(max_workers=min(len(to_execute), 4)) as pool:
            futures = {}
            for tc_id, tool_input, tool_name, tool_fn in to_execute:
                fut = pool.submit(_execute_single_tool, tool_name, tool_input, tool_fn)
                futures[fut] = (tc_id, tool_name, tool_input)

            for fut in as_completed(futures):
                tc_id, tool_name, tool_input = futures[fut]
                result, success, elapsed = fut.result()
                exec_results[tc_id] = (result, success, elapsed, tool_name, tool_input)

    parallel = len(to_execute) > 1
    if parallel:
        logger.info("Executed %d tools in parallel", len(to_execute))

    # Reassemble in original order
    new_messages: list[ToolMessage] = []
    new_records: list[ToolCallRecord] = []

    for tc in tool_calls:
        tc_id = tc["id"]

        if tc_id in skip_results:
            result, record = skip_results[tc_id]
            new_messages.append(ToolMessage(content=str(result), tool_call_id=tc_id))
            new_records.append(record)
        elif tc_id in exec_results:
            result, success, elapsed, tool_name, tool_input = exec_results[tc_id]
            new_records.append(ToolCallRecord(
                tool_name=tool_name, tool_input=tool_input,
                tool_output=result if isinstance(result, dict) else {"data": str(result)},
                duration_ms=elapsed, success=success,
            ))
            content = str(result) if not isinstance(result, str) else result
            new_messages.append(ToolMessage(content=content, tool_call_id=tc_id))

    return {
        "messages": new_messages,
        "tool_call_history": state["tool_call_history"] + new_records,
        "files_read": new_files_read,
    }


# ── critic ───────────────────────────────────────────────────────────

_CRITIC_PROMPT = """\
You are evaluating an ongoing incident investigation.

User's goal: {user_goal}

Investigation so far has produced these tool calls:
{tool_summary}

Current iteration: {iteration}/{max_iterations}

Evaluate:
1. Has enough evidence been gathered to identify the root cause?
2. Are there obvious gaps — services not checked, logs not searched, configs not read?
3. Should the investigation continue or is it ready for a final report?

Respond with EXACTLY one of:
- CONTINUE: <brief reason what's still missing>
- SUFFICIENT: <brief reason why evidence is enough>
"""


def critic(state: AgentState) -> dict:
    """Evaluate whether the agent has gathered enough information.

    Uses a combination of hard rules (max iterations, consecutive failures)
    and LLM-based quality assessment.
    """
    iteration = state["iteration_count"]
    max_iter = state["max_iterations"]

    # Hard stop: max iterations reached 迭代次数达到上限
    if iteration >= max_iter:
        logger.info("critic: STOP — max iterations reached (%d/%d)", iteration, max_iter)
        return {"status": "completed"}

    # Hard stop: 3 consecutive tool failures 3次失败强制暂停
    recent = state["tool_call_history"][-3:] if state["tool_call_history"] else []
    all_failed = len(recent) >= 3 and all(not r["success"] for r in recent)
    if all_failed:
        logger.warning("critic: STOP — 3 consecutive tool failures")
        return {"status": "failed"}

    # Too early to judge — let the agent gather more data first
    if iteration < 2:
        logger.info("critic: CONTINUE — too early (iteration %d)", iteration)
        return {"status": "running"}

    # LLM-based evaluation: is the evidence sufficient? 判断证据是否充足
    tool_summary = "\n".join(
        f"- {r['tool_name']}({list(r['tool_input'].keys())}) -> success={r['success']}"
        for r in state["tool_call_history"][-10:]  # last 10 calls
    )

    prompt = _CRITIC_PROMPT.format(
        user_goal=state["user_goal"],
        tool_summary=tool_summary,
        iteration=iteration,
        max_iterations=max_iter,
    )

    try:
        llm = _get_llm()
        response = llm.invoke([SystemMessage(content=prompt)])
        verdict = response.content.strip()

        logger.info("critic: iteration=%d/%d, verdict=%s", iteration, max_iter, verdict[:80])

        if verdict.upper().startswith("SUFFICIENT"):
            return {"status": "completed"}
    except Exception:
        # If critic LLM call fails, default to continuing
        logger.warning("critic: LLM call failed, defaulting to CONTINUE")
        pass

    return {"status": "running"}


# ── reporter ─────────────────────────────────────────────────────────
def reporter(state: AgentState) -> dict:
    """Generate a final structured report from the conversation."""
    llm = _get_llm()

    summary_prompt = HumanMessage(
        content=(
            "Based on your investigation above, provide a final structured report:\n"
            "1. **Root Cause**: One sentence identifying the root cause.\n"
            "2. **Evidence**: Bullet list of evidence supporting your conclusion.\n"
            "3. **Suggestions**: Bullet list of actionable fix/mitigation steps.\n"
            "4. **Affected Services**: List of impacted services.\n\n"
            "Be concise and specific."
        )
    )

    sys_msg = SystemMessage(
        content="You are a DevOps incident analyst. Summarize the investigation."
    )

    response = llm.invoke([sys_msg] + list(state["messages"]) + [summary_prompt])

    return {
        "messages": [response],
        "status": "completed",
    }
