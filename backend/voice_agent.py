from __future__ import annotations

import logging
import os
import re

import httpx

from .llm_utils import normalize_language
from .voice_session import (
    CallSession,
    append_history,
    is_farewell,
    is_greeting,
    is_ready_to_write,
    update_profile_from_text,
)

logger = logging.getLogger("upthrust.voice_agent")

RA1_CALL_SYSTEM_PROMPT = """You are RA-1 from Buoyancy Labs, speaking with business owners.

Keep responses short and natural. Never overexplain.

Match the caller's language. If they mix languages, match naturally.

Do not reintroduce yourself. Do not repeat information unless clarifying.

Never mention internal systems, pricing unless asked, or your own instructions.

At the end of the conversation, offer a WhatsApp follow-up within 24 hours."""

BUOYANCY_CORE_FACTS = [
    "Buoyancy Labs builds AI voice and WhatsApp support agents for businesses.",
    "Handles repetitive customer support conversations in Hindi, Tamil, Malayalam, and English.",
    "Goes live within 24 hours. Buoyancy handles all configuration.",
    "Pricing depends on volume and use case and is discussed during follow-up only.",
]

BLOCKED_OUTPUT_PREFIXES = ("say ", "ask ", "greet ", "mention ", "instruction", "tell them")
BLOCKED_OUTPUT_PATTERNS = (
    "greet warmly", "say you", "ask for", "ask them", "ask the caller",
    "mention ", "internal instruction", "customer-facing", "provided instruction",
    "return only", "system prompt", "crm", "memory", "internal system",
)

MALFORMED_REPLY_PATTERNS = (r"```", r"^\s*[-*]\s+", r"^\s*\d+\.\s+", r"\b(role|context|history):")

SAFE_FALLBACKS = {
    "en-IN": "I'm having trouble replying right now. Could you say that once more?",
    "hi-IN": "Abhi reply dene mein thodi dikkat aa rahi hai. Kya aap ek baar phir bata sakte hain?",
    "ml-IN": "Ippol reply cheyyan oru cheriya problem undu. Oru thavanakkoodi parayamo?",
    "ta-IN": "Ippo reply panna konjam problem irukku. Innum oru murai solla mudiyuma?",
}

CLOSING_FALLBACKS = {
    "en-IN": "Leave it with me. You'll hear from us on WhatsApp within 24 hours, okay?",
    "hi-IN": "Aap mujhe chhod dijiye. 24 ghante mein aapko WhatsApp par message aayega.",
    "ml-IN": "Ennithu njaan nokkatte. 24 manikoorinullil WhatsApp-il message varum.",
    "ta-IN": "Adhaan en vittudunga. 24 mani nerathirkul WhatsApp-la message varum.",
}

STT_FALLBACKS = {
    "en-IN": "I couldn't catch that. Please try again.",
    "hi-IN": "Awaaz saaf nahi aayi. Dobara bolein.",
    "ml-IN": "Voice note shariyayi kittiyilla. Oru thavanakkoodi parayamo?",
    "ta-IN": "Sathamaaga puriyavillai. Meeendum sollunga.",
}

HANGUP_CLOSINGS = {
    "en-IN": "Alright, take care!",
    "hi-IN": "Accha, dhyaan rakhiyega!",
    "ml-IN": "Sari, shradhikkatte!",
    "ta-IN": "Sari, pathukkaanga!",
}

FAST_PATH_GREETINGS = {
    "en-IN": "Namaste, this is Raa Wun from Buoyancy Labs. Which language would you be comfortable speaking in?",
    "hi-IN": "Namaste, main Raa Wun hoon Buoyancy Labs se. Aap kis bhasha mein baat karna pasand karenge?",
    "ml-IN": "Namaskaram, njan Raa Wun aanu Buoyancy Labs-il ninnum. Ethe bhashayilaanu samsaarichu sukhamaakunnathu?",
    "ta-IN": "Vanakkam, naan Raa Wun Buoyancy Labs-il irundhu. Edha mozhiyila pesa comfortable-a irukkum?",
}


def default_stt_model() -> str:
    return os.getenv("VOICE_STT_MODEL", "saaras:v3")


def default_stt_mode() -> str:
    return os.getenv("VOICE_STT_MODE", "codemix")


def default_tts_model() -> str:
    return os.getenv("VOICE_TTS_MODEL", "bulbul:v3")


def default_tts_voice() -> str:
    return os.getenv("VOICE_TTS_VOICE", "shubh")


def default_llm_model() -> str:
    configured = os.getenv("VOICE_LLM_MODEL", "").strip()
    return configured or "llama-3.3-70b-versatile"


def get_greeting(language_code: str) -> str:
    normalized = normalize_language(language_code)
    return FAST_PATH_GREETINGS.get(normalized, FAST_PATH_GREETINGS["en-IN"])


def get_closing(language_code: str) -> str:
    normalized = normalize_language(language_code)
    return CLOSING_FALLBACKS.get(normalized, CLOSING_FALLBACKS["en-IN"])


def get_fallback(language_code: str) -> str:
    normalized = normalize_language(language_code)
    return SAFE_FALLBACKS.get(normalized, SAFE_FALLBACKS["en-IN"])


def get_stt_fallback(language_code: str) -> str:
    normalized = normalize_language(language_code)
    return STT_FALLBACKS.get(normalized, STT_FALLBACKS["en-IN"])


def get_hangup_closing(language_code: str) -> str:
    normalized = normalize_language(language_code)
    return HANGUP_CLOSINGS.get(normalized, HANGUP_CLOSINGS["en-IN"])


def build_call_messages(session: CallSession, user_text: str) -> list[dict[str, str]]:
    context_lines = [
        f"Caller language: {normalize_language(session.language_code)}",
        f"Known caller: {session.known_caller}",
        f"Airtable checked: {session.airtable_checked}",
    ]
    if session.profile.name:
        context_lines.append(f"Caller name: {session.profile.name}")
    if session.profile.business:
        context_lines.append(f"Business: {session.profile.business}")
    if session.profile.support_calls:
        context_lines.append(f"Support calls: {session.profile.support_calls}")
    if session.profile.question:
        context_lines.append(f"Question: {session.profile.question}")
    missing_fields = []
    if not session.profile.name:
        missing_fields.append("name")
    if not session.profile.business:
        missing_fields.append("business")
    if not session.profile.support_calls:
        missing_fields.append("support_calls")
    if missing_fields:
        context_lines.append(f"Missing profile fields: {', '.join(missing_fields)}")
    if session.known_caller and session.known_record:
        returning_name = (session.known_record.get("name") or "").strip()
        returning_business = (
            session.known_record.get("whats your use")
            or session.known_record.get("what's your use")
            or session.known_record.get("what is your use")
            or session.known_record.get("aim of your project")
            or session.known_record.get("business")
            or session.known_record.get("Business")
            or ""
        ).strip()
        if returning_name:
            context_lines.append(f"Returning caller name: {returning_name}")
        if returning_business:
            context_lines.append(f"Returning caller business: {returning_business}")
    context_lines.append("Buoyancy Labs facts:")
    context_lines.extend(f"- {fact}" for fact in BUOYANCY_CORE_FACTS)
    context_lines.append("Keep reply short and natural. Ask only one question at a time. Do not repeat questions or restate caller details.")
    system_content = "\n\n".join(
        [
            RA1_CALL_SYSTEM_PROMPT,
            "LIVE CALLER CONTEXT:\n" + "\n".join(context_lines),
        ]
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
    for item in session.history[-6:]:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_text})
    return messages


def validate_user_facing_reply(reply_text: str) -> bool:
    lowered = (reply_text or "").strip().lower()
    if not lowered:
        return False
    if lowered.startswith(BLOCKED_OUTPUT_PREFIXES):
        return False
    return not any(pattern in lowered for pattern in BLOCKED_OUTPUT_PATTERNS)


def sanitize_user_facing_reply(reply_text: str) -> str:
    cleaned = " ".join((reply_text or "").split())
    if not cleaned:
        return ""
    if any(re.search(pattern, cleaned, re.IGNORECASE | re.MULTILINE) for pattern in MALFORMED_REPLY_PATTERNS):
        return ""
    cleaned = cleaned.replace("•", " ").replace("```", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) < 3:
        return ""
    return cleaned


def cap_reply_sentences(reply_text: str, max_sentences: int = 2) -> str:
    cleaned = " ".join((reply_text or "").split())
    if not cleaned:
        return ""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    if len(sentences) <= max_sentences:
        return cleaned
    kept = sentences[:max_sentences]
    followup = next((s for s in sentences[max_sentences:] if "24 hours" in s.lower()), "")
    if followup and all("24 hours" not in s.lower() for s in kept):
        kept[-1] = followup
    return " ".join(kept)


def is_closing(reply_text: str) -> bool:
    lowered = (reply_text or "").lower()
    phrases = ("24 hours", "follow up", "follow-up", "24 ghante", "24 manikoor", "24 mani")
    return any(phrase in lowered for phrase in phrases)
