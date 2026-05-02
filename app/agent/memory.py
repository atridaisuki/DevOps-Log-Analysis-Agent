"""Memory management — context window control and message summarization."""

from __future__ import annotations

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from app.config import settings

# Threshold: when messages exceed this count, summarize older ones
MESSAGE_THRESHOLD = 20
# Keep the most recent N messages intact (they have the freshest context)
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


def maybe_compress_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """If the message list is too long, summarize older messages.

    Strategy: keep the first HumanMessage (original goal) and the most
    recent KEEP_RECENT messages. Summarize everything in between into a
    single SystemMessage.
    """
    if len(messages) <= MESSAGE_THRESHOLD:
        return messages

    # Split: first message (user goal) | middle (to summarize) | recent (keep)
    first_msg = messages[0]
    middle = messages[1:-KEEP_RECENT]
    recent = messages[-KEEP_RECENT:]

    # Build a text representation of middle messages for summarization
    middle_text_parts = []
    for msg in middle:
        role = msg.__class__.__name__.replace("Message", "")
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        # Truncate very long tool results
        if len(content) > 500:
            content = content[:500] + "... [truncated]"
        middle_text_parts.append(f"[{role}] {content}")

    middle_text = "\n".join(middle_text_parts)

    llm = _get_llm()
    summary_response = llm.invoke([
        SystemMessage(content="Summarize the following investigation steps concisely. Focus on: what was checked, what was found, what hypotheses were formed or rejected. Keep it under 300 words."),
        HumanMessage(content=middle_text),
    ])

    summary_msg = SystemMessage(
        content=f"[Summary of previous {len(middle)} investigation steps]\n{summary_response.content}"
    )

    return [first_msg, summary_msg] + recent
