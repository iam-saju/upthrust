from __future__ import annotations

import os
from typing import Any

import httpx

from .llm_providers.groq import chat_complete as _groq_complete
from .llm_providers.groq import default_chat_model


def chat_max_tokens() -> int:
    raw = os.getenv("GROQ_CHAT_MAX_TOKENS", os.getenv("SARVAM_CHAT_MAX_TOKENS", "220"))
    try:
        return max(int(raw), 1)
    except ValueError:
        return 220


def extract_text_reply(response_payload: Any) -> str:
    if isinstance(response_payload, dict):
        choices = response_payload.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
    return ""


async def generate_reply(
    client: httpx.AsyncClient,
    messages: list[dict[str, str]],
) -> str:
    try:
        reply = await _generate_once(client, messages)
    except RuntimeError as exc:
        if "empty reply" not in str(exc).lower():
            raise
        reply = await _generate_once(client, force_final_answer_messages(messages), max_tokens=max(chat_max_tokens(), 260))
    normalized = reply.strip()
    if not normalized:
        raise RuntimeError("LLM returned an empty reply")
    return normalized


async def _generate_once(
    client: httpx.AsyncClient,
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
) -> str:
    return await _groq_complete(
        client=client,
        messages=messages,
        model=default_chat_model(),
        max_tokens=max_tokens or chat_max_tokens(),
    )


def force_final_answer_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    if not messages:
        return messages
    forced = [dict(message) for message in messages]
    first = forced[0]
    if first.get("role") == "system":
        first["content"] = (
            "CRITICAL: Output only the final user-visible WhatsApp reply. "
            "Do not include reasoning, analysis, scratchpad, or <think> tags. "
            "Start immediately with the answer in 1 short sentence. "
            f"{first.get('content', '')}"
        )
    return forced
