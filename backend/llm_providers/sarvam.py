from __future__ import annotations

import asyncio
import os
import re

import httpx


def default_chat_model() -> str:
    configured = os.getenv("SARVAM_CHAT_MODEL", "").strip()
    return configured or "sarvam-30b"


def require_sarvam_config() -> str:
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError("Missing Sarvam environment variable: SARVAM_API_KEY")
    return api_key


def chat_timeout_seconds() -> float:
    raw = os.getenv("SARVAM_CHAT_TIMEOUT_MS", "8000")
    try:
        return max(int(raw), 1000) / 1000
    except ValueError:
        return 8.0


def _extract_reply(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return _strip_thinking(content)
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return _strip_thinking(" ".join(parts))
    return ""


def _strip_thinking(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.strip()


async def chat_complete(
    client: httpx.AsyncClient,
    messages: list[dict[str, str]],
    model: str,
    max_tokens: int,
) -> str:
    api_key = require_sarvam_config()
    response = await asyncio.wait_for(
        client.post(
            "https://api.sarvam.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "api-subscription-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.2,
                "top_p": 1,
                "max_tokens": max_tokens,
                "frequency_penalty": 0,
                "presence_penalty": 0,
                "messages": messages,
            },
        ),
        timeout=chat_timeout_seconds(),
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = response.text[:1000]
        raise RuntimeError(f"Sarvam chat failed status={response.status_code} body={body}") from exc
    payload = response.json()
    reply = _extract_reply(payload)
    if not reply:
        raise RuntimeError(f"Sarvam chat returned an empty reply payload={str(payload)[:1000]}")
    return reply
