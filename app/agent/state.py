"""Agent state definition for the LangGraph ReAct loop."""

from __future__ import annotations

from typing import Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class ToolCallRecord(TypedDict):
    """Record of a single tool invocation."""

    tool_name: str
    tool_input: dict
    tool_output: dict
    duration_ms: float
    success: bool


class TokenUsage(TypedDict):
    """Record of token consumption for a single LLM call."""

    node: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float


class AgentState(TypedDict):
    """Full state flowing through the LangGraph agent graph.

    LangGraph automatically passes this between nodes and persists it
    via the checkpointer. The ``messages`` field uses the built-in
    ``add_messages`` reducer so new messages are appended rather than
    replaced.
    """

    # --- user input ---
    user_goal: str
    scenario_path: str

    # --- LLM conversation ---
    messages: Annotated[list[BaseMessage], add_messages]

    # --- planning & reasoning ---
    current_plan: str
    hypotheses: list[str]
    findings: list[str]

    # --- tool tracking ---
    tool_call_history: list[ToolCallRecord]
    files_read: list[str]

    # --- control ---
    iteration_count: int
    max_iterations: int
    status: Literal["running", "completed", "failed"]

    # --- token tracking ---
    token_usage: list[TokenUsage]
