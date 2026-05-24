from __future__ import annotations

from .llm_utils import is_indic_language


def fallback_response(text: str, language_code: str) -> str:
    normalized = (text or "").strip()
    if not normalized:
        if is_indic_language(language_code):
            return "I could not understand that. Please send a short text message or voice note again."
        return "I could not understand that. Please send a short text message or voice note again."

    if is_indic_language(language_code):
        return "I am having trouble responding right now. Please try again in a moment, or send your message again in text."
    return "I am having trouble responding right now. Please try again in a moment, or send your message again in text."

