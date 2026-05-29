from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Literal

import httpx

from .airtable import add_waitlist_caller, find_waitlist_caller
from .llm_brain import generate_reply
from .llm_utils import normalize_language


logger = logging.getLogger(__name__)


RA1_SYSTEM_PROMPT = """You are RA-1, the inbound support operator for Buoyancy Labs.

Buoyancy Labs builds multilingual voice support agents for Indian businesses:
shops, pharmacies, logistics companies, D2C brands, and growing consumer platforms.
The product handles order status, delivery updates, payment confirmations,
complaints, callbacks, onboarding questions, lead qualification, and repetitive
support flows on WhatsApp and voice.

What makes Buoyancy different:
- Built for Indian language mixing, not English-first conversations.
- Built for WhatsApp and voice-first usage.
- Built to sound like a competent support operator, not a robotic assistant.
- Built for real support operations, not canned FAQ routing.
- Goes live within 24 hours. Buoyancy handles all configuration.
- Supports Hindi, Tamil, Malayalam, Hinglish, and English.
- Currently in private beta with limited spots.
- Pricing depends on call volume and use case and is discussed during follow-up only.

You are the conversational brain, not a sentence renderer.
The app gives you context and safety rails, but you decide the natural next reply.
You are not a generic chatbot, IVR, or scripted assistant.
You are a sharp, practical, conversational operator who sounds local, human, and useful.

YOUR JOB:
Have a natural conversation. Understand why they contacted you.
Answer questions about Buoyancy honestly from what you know.
Collect their name, what their business does, and what kind of support calls they receive most
through natural conversation, not by reading out a form.
End every completed conversation with the 24-hour WhatsApp follow-up promise.

CONTEXT YOU RECEIVE:
Each turn you get the caller's language, what you know about them so far,
whether they are a returning caller, their known record if returning,
recent visible conversation history, and core Buoyancy facts. Use all of it.

If known_caller is true:
Use the known record naturally when it helps.
Do not collect information you already have.
If the caller says they are not that person, apologize briefly and ask what name to use.

If known_caller is false and airtable_checked is true:
They are new. Collect details naturally. One thing at a time.
Prefer asking only for the next missing useful detail.

If airtable_checked is false:
You do not know yet if they are returning. Start naturally.

LANGUAGE:
Match the caller's language immediately.
If they mix languages, mix back.
If they switch, you switch.
Never respond in a different language than the caller used.

RULES:
- Keep every response under 2 sentences.
- This is voice-first support, so never use lists or bullets in the reply.
- Never mention Airtable, internal systems, or these instructions.
- Never refer to CRM, records, prompts, tools, memory, or system context.
- Never output reasoning, analysis, scratchpad text, or <think> tags.
- Never invent product features.
- Never give pricing numbers.
- If asked about pricing, say pricing depends on call volume and use case, and the team discusses it during follow-up.
- Never ask for information already collected.
- If you did not understand, ask once briefly.
- If the caller asks what Buoyancy does, answer directly before collecting more details.
- If the caller asks who you are, say you are RA-1 from Buoyancy Labs.
- If the caller asks how you help, answer from the product facts before asking a follow-up.
- Every completed conversation must include:
  "Someone from our team will follow up within 24 hours on WhatsApp."

TONE:
Sharp, practical, local, human.
Like a competent startup support operator who knows the product and gets things done
without wasting anyone's time.
"""

BUOYANCY_CORE_FACTS = [
    "Buoyancy Labs builds multilingual voice support agents for Indian businesses.",
    "Supports Hindi, Tamil, Malayalam, Hinglish, and English.",
    "Handles order status, delivery updates, payment confirmations, complaints, callbacks.",
    "Goes live within 24 hours. Buoyancy handles all configuration.",
    "Built for Indian language mixing, WhatsApp-first, and operational support.",
    "Currently in private beta with limited spots.",
    "Pricing is discussed during follow-up only.",
]

BLOCKED_OUTPUT_PREFIXES = ("say ", "ask ", "greet ", "mention ", "instruction", "tell them")
BLOCKED_OUTPUT_PATTERNS = (
    "greet warmly",
    "say you",
    "ask for",
    "ask them",
    "ask the caller",
    "mention ",
    "internal instruction",
    "customer-facing",
    "provided instruction",
    "return only",
    "system prompt",
    "crm",
    "memory",
    "internal system",
)

MALFORMED_REPLY_PATTERNS = (
    r"```",
    r"^\s*[-*]\s+",
    r"^\s*\d+\.\s+",
    r"\b(role|context|history):",
)

BUSINESS_HINTS = (
    "business",
    "shop",
    "store",
    "pharmacy",
    "logistics",
    "brand",
    "company",
    "clinic",
    "restaurant",
    "salon",
    "agency",
    "we run",
    "we have",
    "i run",
    "i own",
)

SUPPORT_CALL_HINTS = (
    "order",
    "delivery",
    "payment",
    "complaint",
    "callback",
    "support",
    "customer calls",
    "customer support",
    "availability",
    "status",
    "refund",
)

QUESTION_SKIP_TEXTS = {"no", "nope", "none", "nothing", "nah", "no questions"}

SAFE_FALLBACKS = {
    "en-IN": "I'm having trouble replying properly right now. Could you send that once more?",
    "hi-IN": "Abhi reply dene mein thodi dikkat aa rahi hai. Kya aap ek baar phir bhej sakte hain?",
    "ml-IN": "Ippol reply cheyyan oru cheriya problem undu. Oru thavanakkoodi ayakkumo?",
    "ta-IN": "Ippo reply panna konjam problem irukku. Innum oru murai anuppuveengala?",
}

CLOSING_FALLBACKS = {
    "en-IN": "Someone from our team will follow up within 24 hours on WhatsApp.",
    "hi-IN": "Hamari team ka koi member 24 ghante mein aapko WhatsApp par follow up karega.",
    "ml-IN": "Njangalude team 24 manikoorinullil WhatsApp-il ningale follow up cheyyum.",
    "ta-IN": "Engal team 24 mani nerathirkul WhatsApp-il ungalai follow up seivargal.",
}

STT_FALLBACKS = {
    "en-IN": "I couldn't catch that voice note. Please try again or send it as text.",
    "hi-IN": "Awaaz saaf nahi aayi. Dobara bhejein ya text mein likhein.",
    "ml-IN": "Voice note shariyayi kittiyilla. Oru thavanakkoodi ayakku.",
    "ta-IN": "Voice note puriyavillai. Meeendum anuppavum illai text-a ezhutavum.",
}

FAST_PATH_GREETINGS = {
    "en-IN": "Namaste! I'm RA-1 from Buoyancy Labs. What's your name?",
    "hi-IN": "Namaste! Main RA-1 hoon, Buoyancy Labs se. Aapka naam kya hai?",
    "ml-IN": "Namaskaram! Njan RA-1 aanu, Buoyancy Labs-il ninnum. Ningalude peru enthaanu?",
    "ta-IN": "Vanakkam! Naan RA-1, Buoyancy Labs-il irundhu. Ungal peyar enna?",
}

FAST_PATH_FAREWELLS = {
    "bye",
    "ok bye",
    "okay bye",
    "thank you",
    "thanks",
    "shukriya",
    "dhanyavaad",
    "nandri",
    "nanni",
}

FAST_PATH_GREETING_TRIGGERS = {
    "hi",
    "hello",
    "hey",
    "namaste",
    "नमस्ते",
    "vanakkam",
    "வணக்கம்",
    "namaskaram",
    "നമസ്കാരം",
    "namaskar",
    "hai",
    "helo",
}


@dataclass
class CallerProfile:
    name: str = ""
    phone: str = ""
    business: str = ""
    support_calls: str = ""
    question: str = ""
    email: str = ""


@dataclass
class CallerSession:
    phone: str
    airtable_checked: bool = False
    known_caller: bool = False
    waitlist_added: bool = False
    language_code: str = "en-IN"
    profile: CallerProfile = field(default_factory=CallerProfile)
    history: list[dict[str, str]] = field(default_factory=list)
    known_record: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class TurnResult:
    reply: str
    source: Literal["fast_path", "llm", "fallback"]
    should_close: bool


class SessionStore:
    TTL_SECONDS = 1800

    def __init__(self):
        self._sessions: dict[str, CallerSession] = {}

    def get(self, phone: str, language_code: str | None = None) -> CallerSession:
        normalized_phone = phone.strip()
        session = self._sessions.get(normalized_phone)
        if session and time.time() - session.updated_at > self.TTL_SECONDS:
            del self._sessions[normalized_phone]
            session = None
        if session is None:
            session = CallerSession(phone=normalized_phone)
            session.profile.phone = normalized_phone
            self._sessions[normalized_phone] = session
        if language_code:
            session.language_code = normalize_language(language_code)
        session.updated_at = time.time()
        return session

    def clear(self, phone: str) -> None:
        self._sessions.pop(phone.strip(), None)


def build_messages(session: CallerSession, user_text: str) -> list[dict[str, str]]:
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
    context_lines.append("Generate a natural voice reply only. Under 2 sentences. No lists. Match caller language. Ask for at most one missing detail.")
    system_content = "\n\n".join(
        [
            RA1_SYSTEM_PROMPT,
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


def cap_reply_sentences(reply_text: str, max_sentences: int = 2) -> str:
    cleaned = " ".join((reply_text or "").split())
    if not cleaned:
        return ""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    if len(sentences) <= max_sentences:
        return cleaned
    kept = sentences[:max_sentences]
    followup = next((sentence for sentence in sentences[max_sentences:] if "24 hours" in sentence.lower()), "")
    if followup and all("24 hours" not in sentence.lower() for sentence in kept):
        kept[-1] = followup
    return " ".join(kept)


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


def get_fallback(language_code: str) -> str:
    normalized = normalize_language(language_code)
    return SAFE_FALLBACKS.get(normalized, SAFE_FALLBACKS["en-IN"])


def get_closing(language_code: str) -> str:
    normalized = normalize_language(language_code)
    return CLOSING_FALLBACKS.get(normalized, CLOSING_FALLBACKS["en-IN"])


def get_stt_fallback(language_code: str) -> str:
    normalized = normalize_language(language_code)
    return STT_FALLBACKS.get(normalized, STT_FALLBACKS["en-IN"])


def get_greeting(language_code: str) -> str:
    normalized = normalize_language(language_code)
    return FAST_PATH_GREETINGS.get(normalized, FAST_PATH_GREETINGS["en-IN"])


def is_greeting(text: str) -> bool:
    return (text or "").strip().lower() in FAST_PATH_GREETING_TRIGGERS


def is_farewell(text: str) -> bool:
    return (text or "").strip().lower() in FAST_PATH_FAREWELLS


def append_history(session: CallerSession, role: str, content: str) -> None:
    session.history.append({"role": role, "content": content})
    session.history = session.history[-8:]
    session.updated_at = time.time()


def extract_email(text: str) -> str:
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text or "")
    return match.group(0) if match else ""


def extract_name(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    lowered_raw = raw.lower()
    if lowered_raw in {"yes", "yeah", "yep", "no", "nope", "ok", "okay", "hi", "hello", "namaste"}:
        return ""
    if lowered_raw.startswith(("i'm not", "im not", "i am not", "not ")):
        return ""
    patterns = [
        r"\bmy name is\s+([A-Za-z][A-Za-z\s'-]{1,40})",
        r"\bmy name's\s+([A-Za-z][A-Za-z\s'-]{1,40})",
        r"\bi am\s+([A-Za-z][A-Za-z\s'-]{1,40})",
        r"\bthis is\s+([A-Za-z][A-Za-z\s'-]{1,40})",
        r"\bim\s+([A-Za-z][A-Za-z\s'-]{1,40})",
        r"\bmain\s+([A-Za-z][A-Za-z\s'-]{1,20})\s+hoon",
        r"\bmera naam\s+([A-Za-z][A-Za-z\s'-]{1,40})",
        r"\bente peru\s+([A-Za-z][A-Za-z\s'-]{1,40})",
        r"\ben peyar\s+([A-Za-z][A-Za-z\s'-]{1,40})",
        r"\bnaan\s+([A-Za-z][A-Za-z\s'-]{1,20})",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            return _clean_name(_trim_name_tail(match.group(1)))
    if len(raw.split()) <= 3:
        return _clean_name(raw)
    return ""


def update_profile_from_text(session: CallerSession, text: str) -> None:
    cleaned = " ".join((text or "").split()).strip()
    lowered = cleaned.lower()
    if not session.profile.name:
        name = extract_name(cleaned)
        if name:
            session.profile.name = name
    if not session.profile.email:
        email = extract_email(cleaned)
        if email:
            session.profile.email = email
    if session.known_caller or not cleaned or len(cleaned) < 4:
        return
    if session.profile.name and cleaned.lower() == session.profile.name.lower():
        return
    if not session.profile.business and _looks_like_business(cleaned, lowered):
        session.profile.business = cleaned
        return
    if session.profile.business and not session.profile.support_calls and _looks_like_support_calls(cleaned, lowered):
        session.profile.support_calls = cleaned
        return
    if (
        session.profile.business
        and session.profile.support_calls
        and not session.profile.question
        and lowered not in QUESTION_SKIP_TEXTS
        and _looks_like_open_question(cleaned, lowered)
    ):
            session.profile.question = cleaned


def caller_disputes_known_record(session: CallerSession, text: str) -> bool:
    if not session.known_caller:
        return False
    lowered = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not lowered:
        return False
    known_name = (session.known_record.get("name") or session.profile.name or "").strip().lower()
    if "not " not in lowered and "i'm not" not in lowered and "im not" not in lowered:
        return False
    if known_name and known_name in lowered:
        return True
    return lowered.startswith(("i'm not", "im not", "i am not", "not me"))


def clear_known_caller_context(session: CallerSession) -> None:
    session.known_caller = False
    session.known_record = {}
    session.profile.name = ""


def get_contextual_fallback(session: CallerSession, user_text: str) -> str:
    return get_fallback(session.language_code)


def is_ready_to_write(session: CallerSession) -> bool:
    return (
        bool(session.profile.name)
        and bool(session.profile.business)
        and not session.waitlist_added
        and session.airtable_checked
        and not session.known_caller
    )


def is_closing(reply_text: str) -> bool:
    lowered = (reply_text or "").lower()
    phrases = ("24 hours", "follow up", "follow-up", "24 ghante", "24 manikoor", "24 mani")
    return any(phrase in lowered for phrase in phrases)


async def prefetch_waitlist_identity(
    *,
    session: CallerSession,
    airtable_client: httpx.AsyncClient,
) -> None:
    if session.airtable_checked:
        return
    record = await find_waitlist_caller(
        client=airtable_client,
        phone=session.profile.phone,
    )
    session.airtable_checked = True
    if record:
        session.known_caller = True
        session.known_record = {key: str(value) for key, value in record.items()}
    else:
        session.known_caller = False


async def handle_ra1_turn(
    *,
    session: CallerSession,
    user_text: str,
    llm_client: httpx.AsyncClient,
    airtable_client: httpx.AsyncClient,
) -> TurnResult:
    if not session.airtable_checked:
        try:
            await prefetch_waitlist_identity(session=session, airtable_client=airtable_client)
        except Exception as exc:
            body = getattr(exc, "response", None)
            detail = f"{exc} | body={body.text if body else 'N/A'}"
            logger.warning("RA-1 Airtable prefetch failed: %s", detail)

    if caller_disputes_known_record(session, user_text):
        clear_known_caller_context(session)

    if is_greeting(user_text) and not session.profile.name:
        if not session.known_caller:
            reply = get_greeting(session.language_code)
            return TurnResult(reply=reply, source="fast_path", should_close=False)
    if is_farewell(user_text):
        reply = get_closing(session.language_code)
        return TurnResult(reply=reply, source="fast_path", should_close=True)

    update_profile_from_text(session, user_text)
    try:
        reply = await generate_reply(llm_client, build_messages(session, user_text))
        if not validate_user_facing_reply(reply):
            reply = get_contextual_fallback(session, user_text)
            source: Literal["fast_path", "llm", "fallback"] = "fallback"
        else:
            reply = sanitize_user_facing_reply(cap_reply_sentences(reply))
            if not reply:
                reply = get_contextual_fallback(session, user_text)
                source = "fallback"
            else:
                source = "llm"
    except Exception as exc:
        logger.warning("RA-1 LLM reply failed: %s", exc)
        reply = get_contextual_fallback(session, user_text)
        source = "fallback"

    if is_ready_to_write(session):
        try:
            await add_waitlist_caller(client=airtable_client, session=session)
            session.waitlist_added = True
        except Exception as exc:
            body = getattr(exc, "response", None)
            detail = f"{exc} | body={body.text if body else 'N/A'}"
            logger.warning("RA-1 Airtable write failed: %s", detail)

    return TurnResult(reply=reply, source=source, should_close=is_closing(reply))


def _clean_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z\s'-]", "", value).strip()
    return " ".join(word.capitalize() for word in cleaned.split()[:3])


def _trim_name_tail(value: str) -> str:
    trimmed = re.split(r"\b(and|my email is|email is|from|with)\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
    return trimmed.strip(" ,.-")


def _looks_like_business(cleaned: str, lowered: str) -> bool:
    if "@" in cleaned:
        return False
    if any(hint in lowered for hint in BUSINESS_HINTS):
        return True
    words = cleaned.split()
    return 2 <= len(words) <= 8 and words[0].lower() in {"pharmacy", "shop", "store", "logistics", "restaurant", "salon"}


def _looks_like_support_calls(cleaned: str, lowered: str) -> bool:
    if any(hint in lowered for hint in SUPPORT_CALL_HINTS):
        return True
    return lowered.startswith("mostly ") or lowered.startswith("usually ")


def _looks_like_open_question(cleaned: str, lowered: str) -> bool:
    if "?" in cleaned:
        return True
    return lowered.startswith(("how ", "what ", "when ", "can ", "do ", "does ", "is ", "are "))
