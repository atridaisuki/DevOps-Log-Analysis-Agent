"""LangGraph agent graph — ReAct loop with planner, tools, critic, reporter."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph

from app.agent.nodes import critic, planner, reporter, tool_executor
from app.agent.state import AgentState
from app.config import settings


def _should_use_tools(state: AgentState) -> str:
    """Route after planner: if the LLM requested tool calls, go to executor."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tool_executor"
    return "reporter"


def _should_continue(state: AgentState) -> str:
    """Route after critic: continue the loop or finish."""
    if state["status"] in ("completed", "failed"):
        return "reporter"
    return "planner"


def build_graph() -> StateGraph:
    """Construct and compile the agent graph.

    Graph structure:
        START → planner → (has tool calls?) → tool_executor → critic → (enough?) → planner ...
                                            └─ (no tools)  → reporter → END
                                                              ↑ critic routes here when done
    """
    graph = StateGraph(AgentState)#创建图，定义state

    #注册节点
    graph.add_node("planner", planner)
    graph.add_node("tool_executor", tool_executor)
    graph.add_node("critic", critic)#检查是否异常
    graph.add_node("reporter", reporter)

    # Entry point 起点
    graph.set_entry_point("planner")

    # 连边
    # add edge 固定边 conditional edge 条件边

    # Conditional: planner → tool_executor or reporter
    graph.add_conditional_edges(
        "planner",
        _should_use_tools,#检查是否有tool calls
        {"tool_executor": "tool_executor", "reporter": "reporter"},
    )

    # tool_executor → critic
    graph.add_edge("tool_executor", "critic")

    # Conditional: critic → planner (continue) or reporter (done)
    graph.add_conditional_edges(
        "critic",
        _should_continue,#看status
        {"planner": "planner", "reporter": "reporter"},
    )

    # Conditional: reporter → planner (user unsatisfied) or END (done)
    graph.add_conditional_edges(
        "reporter",
        lambda state: "planner" if state["status"] == "running" else END,
        {"planner": "planner", END: END},
    )

    # Choose checkpointer based on config
    if settings.database_url:
        from psycopg import Connection
        from langgraph.checkpoint.postgres import PostgresSaver
        conn = Connection.connect(settings.database_url)
        checkpointer = PostgresSaver(conn)
        checkpointer.setup()  # create tables if not exist
    else:
        from langgraph.checkpoint.sqlite import SqliteSaver
        db_path = Path("data/checkpoints.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        checkpointer = SqliteSaver(conn)

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_after=["reporter"],  # Human-in-the-loop: pause after report so user can review
    )
