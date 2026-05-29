from __future__ import annotations

import re
import time
from dataclasses import dataclass, field


@dataclass
class CallProfile:
    name: str = ""
    phone: str = ""
    business: str = ""
    support_calls: str = ""
    question: str = ""
    email: str = ""


@dataclass
class CallSession:
    phone: str
    airtable_checked: bool = False
    known_caller: bool = False
    waitlist_added: bool = False
    language_code: str = "en-IN"
    profile: CallProfile = field(default_factory=CallProfile)
    history: list[dict[str, str]] = field(default_factory=list)
    known_record: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class CallSessionStore:
    TTL_SECONDS = 1800

    def __init__(self):
        self._sessions: dict[str, CallSession] = {}

    def get(self, phone: str, language_code: str | None = None) -> CallSession:
        normalized_phone = phone.strip()
        session = self._sessions.get(normalized_phone)
        if session and time.time() - session.updated_at > self.TTL_SECONDS:
            del self._sessions[normalized_phone]
            session = None
        if session is None:
            session = CallSession(phone=normalized_phone)
            session.profile.phone = normalized_phone
            self._sessions[normalized_phone] = session
        if language_code:
            session.language_code = language_code
        session.updated_at = time.time()
        return session

    def clear(self, phone: str) -> None:
        self._sessions.pop(phone.strip(), None)


GREETING_TRIGGERS = {
    "hi", "hello", "hey", "namaste", "नमस्ते",
    "vanakkam", "வணக்கம்", "namaskaram", "നമസ്കാരം",
    "namaskar", "hai", "helo",
}

FAREWELL_TRIGGERS = {
    "bye", "ok bye", "okay bye", "thank you", "thanks",
    "shukriya", "dhanyavaad", "nandri", "nanni",
}

BUSINESS_HINTS = (
    "business", "shop", "store", "pharmacy", "logistics",
    "brand", "company", "clinic", "restaurant", "salon",
    "agency", "we run", "we have", "i run", "i own",
)

SUPPORT_CALL_HINTS = (
    "order", "delivery", "payment", "complaint", "callback",
    "support", "customer calls", "customer support",
    "availability", "status", "refund",
)

QUESTION_SKIP_TEXTS = {"no", "nope", "none", "nothing", "nah", "no questions"}


def is_greeting(text: str) -> bool:
    return (text or "").strip().lower() in GREETING_TRIGGERS


def is_farewell(text: str) -> bool:
    return (text or "").strip().lower() in FAREWELL_TRIGGERS


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


def update_profile_from_text(session: CallSession, text: str) -> None:
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


def append_history(session: CallSession, role: str, content: str) -> None:
    session.history.append({"role": role, "content": content})
    session.history = session.history[-8:]
    session.updated_at = time.time()


def is_ready_to_write(session: CallSession) -> bool:
    return (
        bool(session.profile.name)
        and bool(session.profile.business)
        and not session.waitlist_added
        and session.airtable_checked
        and not session.known_caller
    )


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
