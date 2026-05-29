from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .llm_brain import generate_reply
from .llm_utils import normalize_language


DIRECT_LLM_SYSTEM_PROMPT = (
    "You are RA-1, an AI customer support agent powered by Buoyancy Labs. "
    "Buoyancy Labs builds multilingual WhatsApp and voice support agents for Indian businesses. "
    "You are demonstrating how Buoyancy's WhatsApp AI support agent could naturally handle "
    "customer conversations for the user's business through text and voice. "
    "When a business type is provided, respond as the deployed AI support assistant for that business. "
    "Do not say roleplay, pretend, simulation, demo mechanics, or internal instructions unless the user explicitly asks. "
    "Keep responses concise, realistic, warm, and voice-friendly, ideally 1 short sentence and never more than 2. "
    "If speech recognition slightly misspells Buoyancy Labs, infer the user means Buoyancy Labs. "
    "If no business type is known, briefly explain Buoyancy and ask what business they run. "
    "Pricing is discussed during follow-up only; do not invent prices. "
    "Do not show reasoning, analysis, scratchpad text, markdown, or <think> tags."
)
DIRECT_LLM_FALLBACK = "Sorry, I'm having trouble replying right now. Please try again."
DIRECT_STT_FALLBACK = "I couldn't catch that voice note. Please try again or send it as text."
DEMO_INTRO = (
    "Hi, I'm RA-1 from Buoyancy Labs. I can act as an AI customer support agent "
    "for your business over WhatsApp voice and text. What business do you run?"
)
PRODUCT_INTRO = (
    "Buoyancy Labs builds WhatsApp and voice AI support agents for Indian businesses. "
    "What business do you run?"
)
GREETING_TEXTS = {"hi", "hello", "hey", "namaste", "hai", "helo"}
BUOYANCY_MISHEARINGS = (
    "poinsettia labs",
    "poinsettia lapse",
    "buoyancy lapse",
    "buoyancy lab",
    "boyancy labs",
)
PRODUCT_QUESTION_TERMS = (
    "what does buoyancy",
    "what is buoyancy",
    "whats buoyancy",
    "what's buoyancy",
    "who are you",
    "what do you do",
    "how do you help",
    "how can you help",
    "how does buoyancy",
)


@dataclass
class ConversationResult:
    reply: str
    source: str
    airtable_status: str = "disabled"


@dataclass
class DirectCallerSession:
    phone: str
    business_type: str = ""
    history: list[dict[str, str]] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)


class DirectSessionStore:
    TTL_SECONDS = 1800

    def __init__(self):
        self._sessions: dict[str, DirectCallerSession] = {}

    def get(self, phone: str) -> DirectCallerSession:
        normalized_phone = phone.strip()
        session = self._sessions.get(normalized_phone)
        if session and time.time() - session.updated_at > self.TTL_SECONDS:
            del self._sessions[normalized_phone]
            session = None
        if session is None:
            session = DirectCallerSession(phone=normalized_phone)
            self._sessions[normalized_phone] = session
        session.updated_at = time.time()
        return session


def direct_session_business(session: DirectCallerSession) -> str:
    return session.business_type


def build_direct_llm_messages(
    user_text: str,
    language_code: str,
    session: DirectCallerSession | None = None,
    known_name: str = "",
    known_business: str = "",
) -> list[dict[str, str]]:
    business_type = (session.business_type if session else "") or known_business
    context_lines = [
        DIRECT_LLM_SYSTEM_PROMPT,
        f"Target language code: {normalize_language(language_code)}.",
    ]
    if business_type:
        context_lines.append(f"Business type: {business_type}.")
        context_lines.append(
            "Respond as the deployed WhatsApp AI support assistant for this business, "
            "using the business context to infer realistic support behavior."
        )
    else:
        context_lines.append("Business type: not known yet.")

    messages = [{"role": "system", "content": " ".join(context_lines)}]
    if session:
        messages.extend(_safe_history(session.history[-6:]))
    messages.append({"role": "user", "content": user_text})
    return messages


async def handle_direct_turn(
    *,
    logger: logging.Logger | Any,
    llm_client: httpx.AsyncClient,
    airtable_client: httpx.AsyncClient,
    session: DirectCallerSession,
    user_text: str,
    language_code: str,
) -> ConversationResult:
    del airtable_client
    text = normalize_common_stt_mishearings((user_text or "").strip())
    if not text:
        return ConversationResult(reply=DIRECT_LLM_FALLBACK, source="direct_fallback")

    if not session.business_type:
        business_type = extract_business_type(text)
        if business_type:
            session.business_type = business_type
            reply = business_captured_reply(business_type)
            append_history(session, "user", text)
            append_history(session, "assistant", reply)
            return ConversationResult(reply=reply, source="business_captured")
        if is_product_question(text):
            append_history(session, "user", text)
            append_history(session, "assistant", PRODUCT_INTRO)
            return ConversationResult(reply=PRODUCT_INTRO, source="product_intro")
        append_history(session, "user", text)
        append_history(session, "assistant", DEMO_INTRO)
        return ConversationResult(reply=DEMO_INTRO, source="demo_intro")

    new_business_type = extract_explicit_business_type(text)
    if new_business_type and new_business_type.lower() != session.business_type.lower():
        session.business_type = new_business_type
        reply = business_captured_reply(new_business_type)
        append_history(session, "user", text)
        append_history(session, "assistant", reply)
        return ConversationResult(reply=reply, source="business_updated")

    try:
        messages = build_direct_llm_messages(text, language_code, session=session)
        reply = await generate_reply(llm_client, messages)
        append_history(session, "user", text)
        append_history(session, "assistant", reply)
        return ConversationResult(reply=reply, source="direct_llm")
    except Exception as exc:
        logger.warning("Direct LLM reply failed: %s: %s", type(exc).__name__, exc)
        append_history(session, "user", text)
        append_history(session, "assistant", DIRECT_LLM_FALLBACK)
        return ConversationResult(reply=DIRECT_LLM_FALLBACK, source="direct_fallback")


def append_history(session: DirectCallerSession, role: str, content: str) -> None:
    cleaned = " ".join((content or "").split())
    if role not in {"user", "assistant"} or not cleaned:
        return
    session.history.append({"role": role, "content": cleaned})
    session.history = session.history[-8:]
    session.updated_at = time.time()


def business_captured_reply(business_type: str) -> str:
    return (
        f"Got it. I can handle support for your {business_type} over WhatsApp voice and text. "
        "You can message me like a customer would."
    )


def is_greeting_text(text: str) -> bool:
    return (text or "").strip().lower() in GREETING_TEXTS


def is_product_question(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return any(term in lowered for term in PRODUCT_QUESTION_TERMS)


def normalize_common_stt_mishearings(text: str) -> str:
    cleaned = text or ""
    lowered = cleaned.lower()
    for phrase in BUOYANCY_MISHEARINGS:
        if phrase in lowered:
            return re.sub(re.escape(phrase), "Buoyancy Labs", cleaned, flags=re.IGNORECASE)
    return cleaned


def extract_business_type(text: str) -> str:
    raw = " ".join((text or "").split())
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered in GREETING_TEXTS or lowered in {"ok", "okay", "yes", "no", "what", "why", "how", "?"}:
        return ""
    if is_product_question(raw):
        return ""
    patterns = [
        r"\bi\s+run\s+(?:a|an|the)?\s*(.+)",
        r"\bwe\s+run\s+(?:a|an|the)?\s*(.+)",
        r"\bi\s+have\s+(?:a|an|the)?\s*(.+)",
        r"\bwe\s+have\s+(?:a|an|the)?\s*(.+)",
        r"\bmy\s+business\s+is\s+(?:a|an|the)?\s*(.+)",
        r"\bour\s+business\s+is\s+(?:a|an|the)?\s*(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            return clean_business_type(match.group(1))
    if "?" not in raw and len(raw.split()) <= 5:
        return clean_business_type(raw)
    return ""


def extract_explicit_business_type(text: str) -> str:
    raw = " ".join((text or "").split())
    if not raw or is_product_question(raw):
        return ""
    patterns = [
        r"\bi\s+run\s+(?:a|an|the)?\s*(.+)",
        r"\bwe\s+run\s+(?:a|an|the)?\s*(.+)",
        r"\bi\s+have\s+(?:a|an|the)?\s*(.+)",
        r"\bwe\s+have\s+(?:a|an|the)?\s*(.+)",
        r"\bmy\s+business\s+is\s+(?:a|an|the)?\s*(.+)",
        r"\bour\s+business\s+is\s+(?:a|an|the)?\s*(.+)",
        r"\bactually\s+(?:i|we)\s+run\s+(?:a|an|the)?\s*(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            return clean_business_type(match.group(1))
    return ""


def clean_business_type(value: str) -> str:
    cleaned = (value or "").strip()
    cleaned = re.sub(r"\b(and|that|which)\b.*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\b(my name is|i am|this is)\b.*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = cleaned.rstrip(".!?").strip()
    cleaned = re.sub(r"^(a|an|the)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+business$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned[:80]


def _safe_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    safe = []
    for item in history:
        role = item.get("role")
        content = " ".join((item.get("content") or "").split())
        if role in {"user", "assistant"} and content:
            safe.append({"role": role, "content": content})
    return safe
