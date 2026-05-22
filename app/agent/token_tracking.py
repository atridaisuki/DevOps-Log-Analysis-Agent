"""Token usage tracking and cost calculation."""

from __future__ import annotations

from app.agent.state import TokenUsage

PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0, "cache_read": 0.30},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0, "cache_read": 0.08},
    "deepseek-chat": {"input": 0.27, "output": 1.10, "cache_read": 0.07},
    "deepseek-v4-pro": {"input": 0.27, "output": 1.10, "cache_read": 0.07},
}


def calculate_cost(usage: dict, model: str) -> float:
    prices = PRICING.get(model, PRICING["claude-sonnet-4-20250514"])
    input_cost = usage.get("input_tokens", 0) / 1_000_000 * prices["input"]
    output_cost = usage.get("output_tokens", 0) / 1_000_000 * prices["output"]
    cache_cost = usage.get("cache_read_input_tokens", 0) / 1_000_000 * prices["cache_read"]
    return round(input_cost + output_cost + cache_cost, 6)


def extract_token_usage(response, node: str, model: str) -> TokenUsage:
    usage = getattr(response, "response_metadata", {}).get("usage", {})
    if not usage:
        usage = getattr(response, "usage_metadata", {}) or {}
    return TokenUsage(
        node=node,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        cost_usd=calculate_cost(usage, model),
    )


def summarize_usage(token_usage: list[TokenUsage]) -> dict:
    """Aggregate token usage into a summary report."""
    if not token_usage:
        return {"total_input": 0, "total_output": 0, "total_cost_usd": 0.0, "by_node": {}}

    total_input = sum(u["input_tokens"] for u in token_usage)
    total_output = sum(u["output_tokens"] for u in token_usage)
    total_cache = sum(u["cache_read_tokens"] for u in token_usage)
    total_cost = sum(u["cost_usd"] for u in token_usage)

    by_node: dict[str, dict] = {}
    for u in token_usage:
        node = u["node"]
        if node not in by_node:
            by_node[node] = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0}
        by_node[node]["input_tokens"] += u["input_tokens"]
        by_node[node]["output_tokens"] += u["output_tokens"]
        by_node[node]["cost_usd"] += u["cost_usd"]
        by_node[node]["calls"] += 1

    return {
        "total_input": total_input,
        "total_output": total_output,
        "total_cache_read": total_cache,
        "total_cost_usd": round(total_cost, 6),
        "by_node": {
            k: {**v, "cost_usd": round(v["cost_usd"], 6), "pct": round(v["cost_usd"] / total_cost * 100, 1) if total_cost > 0 else 0}
            for k, v in by_node.items()
        },
    }
