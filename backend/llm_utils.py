from __future__ import annotations

LANGUAGE_ALIASES = {
    "en": "en-IN",
    "en-in": "en-IN",
    "hi": "hi-IN",
    "hi-in": "hi-IN",
    "ta": "ta-IN",
    "ta-in": "ta-IN",
    "te": "te-IN",
    "te-in": "te-IN",
    "ml": "ml-IN",
    "ml-in": "ml-IN",
    "kn": "kn-IN",
    "kn-in": "kn-IN",
    "mr": "mr-IN",
    "mr-in": "mr-IN",
    "bn": "bn-IN",
    "bn-in": "bn-IN",
    "gu": "gu-IN",
    "gu-in": "gu-IN",
    "pa": "pa-IN",
    "pa-in": "pa-IN",
}

INDIC_LANGUAGE_PREFIXES = {"hi", "ta", "te", "ml", "kn", "mr", "bn", "gu", "pa"}


def normalize_language(language_code: str | None) -> str:
    if not language_code:
        return "en-IN"

    lowered = language_code.strip().lower()
    return LANGUAGE_ALIASES.get(lowered, language_code.strip())


def is_indic_language(language_code: str | None) -> bool:
    normalized = normalize_language(language_code)
    return normalized.split("-", 1)[0].lower() in INDIC_LANGUAGE_PREFIXES

