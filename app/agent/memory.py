"""Memory management — context window control and message summarization."""

from __future__ import annotations

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.agent.token_tracking import extract_token_usage
from app.config import settings

MESSAGE_THRESHOLD = 20
KEEP_RECENT = 8


def _get_llm() -> ChatAnthropic:
    kwargs: dict = {
        "model": settings.anthropic_model,
        "api_key": settings.anthropic_api_key,
        "max_tokens": 1024,
    }
    if settings.anthropic_base_url:
        kwargs["base_url"] = settings.anthropic_base_url
    return ChatAnthropic(**kwargs)


def _find_safe_split(messages: list[BaseMessage], target_recent: int) -> int:
    """Find a split index that doesn't break tool_use/tool_result pairs.

    Returns the index where 'recent' should start. Ensures that if recent
    starts with ToolMessages, we include the preceding AIMessage with tool_calls.
    """
    split = len(messages) - target_recent

    # Walk backwards from split to ensure we don't start in the middle of a tool pair
    while split > 1 and isinstance(messages[split], ToolMessage):
        split -= 1

    return split


def maybe_compress_messages(messages: list[BaseMessage]) -> tuple[list[BaseMessage], dict | None]:
    """If the message list is too long, summarize older messages.

    Returns (compressed_messages, token_usage_record_or_None).
    """
    if len(messages) <= MESSAGE_THRESHOLD:
        return messages, None

    first_msg = messages[0]
    split_idx = _find_safe_split(messages, KEEP_RECENT)
    middle = messages[1:split_idx]
    recent = messages[split_idx:]

    if not middle:
        return messages, None

    middle_text_parts = []
    for msg in middle:
        role = msg.__class__.__name__.replace("Message", "")
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if len(content) > 500:
            content = content[:500] + "... [truncated]"
        middle_text_parts.append(f"[{role}] {content}")

    middle_text = "\n".join(middle_text_parts)

    llm = _get_llm()
    summary_response = llm.invoke([
        SystemMessage(content="Summarize the following investigation steps concisely. Focus on: what was checked, what was found, what hypotheses were formed or rejected. Keep it under 300 words."),
        HumanMessage(content=middle_text),
    ])

    usage_record = extract_token_usage(summary_response, "compress", settings.anthropic_model)

    raw_content = summary_response.content
    if isinstance(raw_content, list):
        summary_text = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in raw_content
        )
    else:
        summary_text = raw_content

    summary_msg = HumanMessage(
        content=f"[Summary of previous {len(middle)} investigation steps]\n{summary_text}"
    )

    return [first_msg, summary_msg] + recent, usage_record
