from __future__ import annotations

from typing import Any


def extract_text_reply(response_payload: Any) -> str:
    if isinstance(response_payload, dict):
        choices = response_payload.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
    return ""
