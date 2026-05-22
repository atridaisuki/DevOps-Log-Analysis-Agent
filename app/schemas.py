from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    goal: str = Field(..., description="故障描述，例如 'API 响应超时'")
    scenario: str = Field(..., description="故障场景目录名，例如 'scenario_01_db_pool'")
    session_id: str | None = Field(None, description="会话 ID，传入则复用上次状态")
    max_iterations: int = Field(10, ge=1, le=30)
    auto_approve: bool = Field(True, description="自动跳过 human-in-the-loop 确认")


class ToolTrace(BaseModel):
    tool_name: str
    tool_input: dict
    tool_output: dict
    duration_ms: float
    success: bool


class TokenUsageSummary(BaseModel):
    total_input: int = 0
    total_output: int = 0
    total_cache_read: int = 0
    total_cost_usd: float = 0.0
    by_node: dict = Field(default_factory=dict)


class AnalyzeResponse(BaseModel):
    session_id: str
    status: str
    root_cause: str
    findings: list[str]
    suggestions: list[str]
    tool_trace: list[ToolTrace]
    iterations: int
    total_duration_ms: float
    token_usage: TokenUsageSummary | None = None
