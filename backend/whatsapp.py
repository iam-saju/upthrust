from __future__ import annotations

import logging
import os
import time
from base64 import b64decode
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from .fallbacks import fallback_response
from .llm_brain import extract_text_reply
from .ra1 import (
    BehaviorPlan,
    CallerSession,
    SessionStore,
    append_history,
    build_render_request,
    build_ra1_messages,
    cap_reply_sentences,
    decide_turn,
    format_waitlist_business,
    local_ra1_fallback,
    scripted_ra1_reply,
    validate_user_facing_reply,
)
from .llm_utils import normalize_language


class StageTimer:
    def __init__(self):
        self.stages: dict[str, int] = {}
        self._start: float | None = None
        self._t0 = time.time()

    def start(self, stage: str):
        self._start = time.time()
        self._current = stage

    def end(self, stage: str):
        if self._start:
            self.stages[f"{stage}_ms"] = int((time.time() - self._start) * 1000)
            self._start = None

    def total_ms(self) -> int:
        return int((time.time() - self._t0) * 1000)

    def summary(self, kind: str, source: str, language: str):
        return {
            "kind": kind,
            "source": source,
            "language": language,
            **self.stages,
            "total_ms": self.total_ms(),
        }


def whatsapp_graph_version() -> str:
    return os.getenv("WHATSAPP_GRAPH_VERSION", "v25.0")


def whatsapp_base() -> str:
    return f"https://graph.facebook.com/{whatsapp_graph_version()}"


def whatsapp_verify_token() -> str | None:
    return os.getenv("WHATSAPP_VERIFY_TOKEN")


def whatsapp_access_token() -> str | None:
    return os.getenv("WHATSAPP_ACCESS_TOKEN")


def whatsapp_phone_number_id() -> str | None:
    return os.getenv("WHATSAPP_PHONE_NUMBER_ID")


def sarvam_api_key() -> str | None:
    return os.getenv("SARVAM_API_KEY")


def airtable_api_key() -> str | None:
    return os.getenv("AIRTABLE_API_KEY")


def airtable_base_id() -> str | None:
    return os.getenv("AIRTABLE_BASE_ID")


def airtable_waitlist_table() -> str:
    return os.getenv("AIRTABLE_WAITLIST_TABLE_NAME", os.getenv("AIRTABLE_SETUP_TABLE_NAME", "waitinlist"))


def require_whatsapp_config() -> tuple[str, str]:
    access_token = whatsapp_access_token()
    phone_number_id = whatsapp_phone_number_id()
    missing = []
    if not access_token:
        missing.append("WHATSAPP_ACCESS_TOKEN")
    if not phone_number_id:
        missing.append("WHATSAPP_PHONE_NUMBER_ID")
    if missing:
        raise RuntimeError(f"Missing WhatsApp environment variables: {', '.join(missing)}")
    return access_token, phone_number_id


def require_sarvam_config() -> str:
    api_key = sarvam_api_key()
    if not api_key:
        raise RuntimeError("Missing Sarvam environment variable: SARVAM_API_KEY")
    return api_key


def require_airtable_config() -> tuple[str, str, str]:
    api_key = airtable_api_key()
    base_id = airtable_base_id()
    table_name = airtable_waitlist_table()
    missing = []
    if not api_key:
        missing.append("AIRTABLE_API_KEY")
    if not base_id:
        missing.append("AIRTABLE_BASE_ID")
    if missing:
        raise RuntimeError(f"Missing Airtable environment variables: {', '.join(missing)}")
    return api_key, base_id, table_name


def airtable_url() -> str:
    _, base_id, table_name = require_airtable_config()
    return f"https://api.airtable.com/v0/{base_id}/{table_name}"


@dataclass
class WhatsAppDeps:
    logger: logging.Logger
    meta_client_getter: Any
    sarvam_client_getter: Any
    airtable_client_getter: Any
    session_store_getter: Any

    def meta_client(self) -> httpx.AsyncClient:
        return self.meta_client_getter()

    def sarvam_client(self) -> httpx.AsyncClient:
        return self.sarvam_client_getter()

    def airtable_client(self) -> httpx.AsyncClient:
        return self.airtable_client_getter()

    def session_store(self) -> SessionStore:
        return self.session_store_getter()


def extract_whatsapp_messages(payload: dict) -> list[dict]:
    messages: list[dict] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages.extend(value.get("messages", []))
    return messages


def message_text_body(message: dict) -> str:
    return (
        message.get("text", {}).get("body")
        or message.get("button", {}).get("text")
        or message.get("interactive", {}).get("button_reply", {}).get("title")
        or ""
    ).strip()


def message_audio_id(message: dict) -> str:
    return (message.get("audio", {}) or {}).get("id", "").strip()


def target_language_for_tts(language_code: str | None) -> str:
    return normalize_language(language_code or os.getenv("WHATSAPP_DEFAULT_LANGUAGE", "en-IN"))


def detect_text_language(text: str) -> str:
    for char in text or "":
        codepoint = ord(char)
        if 0x0900 <= codepoint <= 0x097F:
            return "hi-IN"
        if 0x0D00 <= codepoint <= 0x0D7F:
            return "ml-IN"
        if 0x0B80 <= codepoint <= 0x0BFF:
            return "ta-IN"
        if 0x0C80 <= codepoint <= 0x0CFF:
            return "kn-IN"
        if 0x0A80 <= codepoint <= 0x0AFF:
            return "gu-IN"
    return "en-IN"


def default_tts_speaker() -> str:
    return os.getenv("SARVAM_TTS_SPEAKER", "shubh")


def default_chat_model() -> str:
    return os.getenv("SARVAM_CHAT_MODEL", "sarvam-30b")


def raise_for_meta_status(*, logger: Any, response: httpx.Response, action: str) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        logger.error(
            "WhatsApp Graph API %s failed status=%s body=%s",
            action,
            response.status_code,
            response.text[:1000],
        )
        raise


async def send_whatsapp_text(*, logger: Any, client: httpx.AsyncClient, to: str, body: str) -> None:
    access_token, phone_number_id = require_whatsapp_config()
    response = await client.post(
        f"{whatsapp_base()}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        },
    )
    raise_for_meta_status(logger=logger, response=response, action="send_text")
    logger.info("Sent WhatsApp text to %s", to)


async def upload_whatsapp_media(
    *,
    logger: Any,
    client: httpx.AsyncClient,
    filename: str,
    content_type: str,
    media_bytes: bytes,
) -> str:
    access_token, phone_number_id = require_whatsapp_config()
    response = await client.post(
        f"{whatsapp_base()}/{phone_number_id}/media",
        headers={"Authorization": f"Bearer {access_token}"},
        data={"messaging_product": "whatsapp"},
        files={"file": (filename, media_bytes, content_type)},
    )
    raise_for_meta_status(logger=logger, response=response, action="upload_media")
    media_id = response.json()["id"]
    logger.info("Uploaded WhatsApp media id=%s", media_id)
    return media_id


async def send_whatsapp_audio(
    *,
    logger: Any,
    client: httpx.AsyncClient,
    to: str,
    media_id: str,
) -> None:
    access_token, phone_number_id = require_whatsapp_config()
    response = await client.post(
        f"{whatsapp_base()}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "audio",
            "audio": {"id": media_id},
        },
    )
    raise_for_meta_status(logger=logger, response=response, action="send_audio")
    logger.info("Sent WhatsApp audio to %s", to)


async def fetch_whatsapp_media_metadata(*, client: httpx.AsyncClient, media_id: str) -> dict[str, Any]:
    access_token, _ = require_whatsapp_config()
    response = await client.get(
        f"{whatsapp_base()}/{media_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return response.json()


async def download_whatsapp_media(*, client: httpx.AsyncClient, media_url: str) -> bytes:
    access_token, _ = require_whatsapp_config()
    response = await client.get(
        media_url,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return response.content


async def sarvam_chat_completion(*, client: httpx.AsyncClient, messages: list[dict[str, str]]) -> str:
    response = await client.post(
        "https://api.sarvam.ai/v1/chat/completions",
        headers={
            "api-subscription-key": require_sarvam_config(),
            "Content-Type": "application/json",
        },
        json={
            "model": default_chat_model(),
            "temperature": 0.2,
            "max_tokens": 120,
            "messages": messages,
        },
    )
    response.raise_for_status()
    reply = extract_text_reply(response.json())
    if not reply:
        raise RuntimeError("Sarvam chat returned an empty reply")
    return reply


async def find_waitlist_caller(
    *,
    client: httpx.AsyncClient,
    phone: str,
    name: str = "",
) -> dict[str, Any] | None:
    api_key, _, _ = require_airtable_config()
    normalized_phone = "".join(ch for ch in phone if ch.isdigit())
    response = await client.get(
        airtable_url(),
        headers={"Authorization": f"Bearer {api_key}"},
        params={"filterByFormula": f"{{phone no}} = {normalized_phone}"},
    )
    response.raise_for_status()
    records = response.json().get("records") or []
    if records:
        return records[0].get("fields") or {}

    if name:
        safe_name = name.replace("'", "\\'")
        response = await client.get(
            airtable_url(),
            headers={"Authorization": f"Bearer {api_key}"},
            params={"filterByFormula": f"{{name}} = '{safe_name}'"},
        )
        response.raise_for_status()
        records = response.json().get("records") or []
        if records:
            return records[0].get("fields") or {}

    return None


async def add_waitlist_caller(*, client: httpx.AsyncClient, session: CallerSession) -> dict[str, Any]:
    api_key, _, _ = require_airtable_config()
    normalized_phone = "".join(ch for ch in session.profile.phone if ch.isdigit())
    fields = {
        "name": session.profile.name,
        "mail": session.profile.email,
        "phone no": int(normalized_phone) if normalized_phone else 0,
        "aim of your project": format_waitlist_business(session.profile),
        "Question": session.profile.question,
    }
    response = await client.post(
        airtable_url(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"fields": fields},
    )
    response.raise_for_status()
    return response.json()


async def sarvam_transcribe_audio(
    *,
    client: httpx.AsyncClient,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
) -> tuple[str, str]:
    response = await client.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": require_sarvam_config()},
        data={"model": "saaras:v3", "mode": "transcribe"},
        files={"file": (filename, audio_bytes, content_type)},
    )
    response.raise_for_status()
    payload = response.json()
    transcript = (payload.get("transcript") or "").strip()
    language_code = normalize_language(payload.get("language_code") or os.getenv("WHATSAPP_DEFAULT_LANGUAGE", "en-IN"))
    if not transcript:
        raise RuntimeError("Sarvam STT returned an empty transcript")
    return transcript, language_code


async def sarvam_synthesize_speech(
    *,
    client: httpx.AsyncClient,
    text: str,
    language_code: str,
) -> bytes:
    response = await client.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={
            "api-subscription-key": require_sarvam_config(),
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "target_language_code": target_language_for_tts(language_code),
            "speaker": default_tts_speaker(),
            "model": "bulbul:v3",
            "speech_sample_rate": 24000,
            "output_audio_codec": "mp3",
        },
    )
    response.raise_for_status()
    payload = response.json()
    audios = payload.get("audios") or []
    if not audios:
        raise RuntimeError("Sarvam TTS returned no audio")
    return b64decode(audios[0])


async def generate_ra1_reply_text(
    *,
    deps: WhatsAppDeps,
    client: httpx.AsyncClient,
    session,
    plan: BehaviorPlan,
) -> tuple[str, str]:
    render_request = build_render_request(session, plan)
    scripted_reply = scripted_ra1_reply(render_request)
    if scripted_reply:
        return scripted_reply, "scripted"

    try:
        reply_text = await sarvam_chat_completion(
            client=client,
            messages=build_ra1_messages(session.history, render_request),
        )
        if not validate_user_facing_reply(reply_text):
            deps.logger.warning("Unsafe RA-1 reply blocked: %r", reply_text[:160])
            return local_ra1_fallback(render_request), "fallback"
        return cap_reply_sentences(reply_text), "llm"
    except Exception as exc:
        deps.logger.warning("LLM failed for RA-1 reply intent=%s stage=%s error=%s", plan.intent, session.stage, exc)
        return local_ra1_fallback(render_request), "fallback"


def returning_caller_facts(record: dict[str, str]) -> list[str]:
    facts = []
    name = (record.get("name") or "").strip()
    business = (
        record.get("aim of your project")
        or record.get("business")
        or record.get("Business")
        or ""
    ).strip()
    if name:
        facts.append(f"Caller is a returning contact named {name}.")
    if business:
        facts.append(f"Their business: {business}.")
    facts.append("Their setup is being reviewed by the Buoyancy team.")
    return facts


STT_FALLBACK_MESSAGES = {
    "hi-IN": "Aapki voice note saaf nahi aayi. Dobara bhejein ya text mein likhein.",
    "ml-IN": "Voice note shariyayi kittiyilla. Oru thavanakkoodi ayakku, allenkil text aayi ezhuthu.",
    "ta-IN": "Voice note thelivaga varala. Meendum anuppunga, illai text-a ezhuthunga.",
    "en-IN": "I couldn't catch that voice note clearly. Please try once more or send it as text.",
}


def stt_fallback_message(language_code: str | None) -> str:
    return STT_FALLBACK_MESSAGES.get(normalize_language(language_code), STT_FALLBACK_MESSAGES["en-IN"])


async def prefetch_waitlist_identity(
    *,
    deps: WhatsAppDeps,
    session: CallerSession,
    airtable_client: httpx.AsyncClient,
) -> None:
    if session.airtable_checked:
        return
    try:
        record = await find_waitlist_caller(
            client=airtable_client,
            phone=session.profile.phone,
        )
    except Exception as exc:
        deps.logger.warning("Airtable prefetch failed phone=%s error=%s", session.profile.phone, exc)
        return

    session.airtable_checked = True
    if record:
        session.known_caller = True
        session.known_record = {key: str(value) for key, value in record.items()}
    else:
        session.known_caller = False


async def resolve_turn_plan(
    *,
    session: CallerSession,
    user_text: str,
    airtable_client: httpx.AsyncClient,
) -> tuple[BehaviorPlan, bool]:
    plan = decide_turn(session, user_text)

    if plan.lookup_caller and session.airtable_checked:
        if session.known_caller:
            session.stage = "returning_questions"
            return (
                BehaviorPlan(
                    intent="returning_status",
                    ack="welcome_back",
                    facts=returning_caller_facts(session.known_record),
                    question_to_ask="What would you like help with today?",
                    close_after_reply=False,
                ),
                False,
            )

        session.stage = "collect_business"
        return (BehaviorPlan(intent="ask_business", ack="got_it"), False)

    if plan.lookup_caller:
        record = await find_waitlist_caller(
            client=airtable_client,
            phone=session.profile.phone,
            name=session.profile.name,
        )
        session.airtable_checked = True
        if record:
            session.known_caller = True
            session.known_record = {key: str(value) for key, value in record.items()}
            session.stage = "returning_questions"
            return (
                BehaviorPlan(
                    intent="returning_status",
                    ack="welcome_back",
                    facts=returning_caller_facts(session.known_record),
                    question_to_ask="What would you like help with today?",
                    close_after_reply=False,
                ),
                False,
            )

        session.known_caller = False
        session.stage = "collect_business"
        return (BehaviorPlan(intent="ask_business", ack="got_it"), False)

    if plan.add_waitlist and not session.waitlist_added:
        await add_waitlist_caller(client=airtable_client, session=session)
        session.waitlist_added = True

    return plan, plan.close_after_reply


async def handle_whatsapp_message(*, deps: WhatsAppDeps, message: dict) -> None:
    from_number = message.get("from")
    if not from_number:
        deps.logger.info("Ignoring WhatsApp message without sender: %s", message)
        return

    timer = StageTimer()
    meta_client = deps.meta_client()
    sarvam_client = deps.sarvam_client()
    airtable_client = deps.airtable_client()
    language_code = normalize_language(os.getenv("WHATSAPP_DEFAULT_LANGUAGE", "en-IN"))
    text_body = message_text_body(message)
    audio_id = message_audio_id(message)
    session = deps.session_store().get(from_number, language_code)
    close_after_reply = False

    if text_body:
        language_code = detect_text_language(text_body)
        session.language_code = language_code
        if session.stage == "greet":
            await prefetch_waitlist_identity(
                deps=deps,
                session=session,
                airtable_client=airtable_client,
            )
        append_history(session, "user", text_body)
        timer.start("llm")
        plan, close_after_reply = await resolve_turn_plan(
            session=session,
            user_text=text_body,
            airtable_client=airtable_client,
        )
        reply_text, reply_source = await generate_ra1_reply_text(
            deps=deps,
            client=sarvam_client,
            session=session,
            plan=plan,
        )
        timer.end("llm")
        append_history(session, "assistant", reply_text)
        timer.start("send")
        await send_whatsapp_text(logger=deps.logger, client=meta_client, to=from_number, body=reply_text)
        timer.end("send")
        deps.logger.info("WA_LATENCY %s", timer.summary("text", reply_source, language_code))
        if close_after_reply:
            deps.session_store().clear(from_number)
        return

    if audio_id:
        reply_source = "audio"
        try:
            timer.start("media_metadata")
            media_metadata = await fetch_whatsapp_media_metadata(client=meta_client, media_id=audio_id)
            timer.end("media_metadata")
            media_url = media_metadata["url"]
            mime_type = media_metadata.get("mime_type", "audio/ogg")
            extension = mime_type.split("/")[-1].replace("mpeg", "mp3")

            timer.start("media_download")
            audio_bytes = await download_whatsapp_media(client=meta_client, media_url=media_url)
            timer.end("media_download")
            deps.logger.info("WA_MEDIA downloaded bytes=%s mime=%s", len(audio_bytes), mime_type)

            timer.start("stt")
            transcript, detected_language = await sarvam_transcribe_audio(
                client=sarvam_client,
                audio_bytes=audio_bytes,
                filename=f"inbound.{extension}",
                content_type=mime_type,
            )
            timer.end("stt")
            deps.logger.info("WA_STT transcript=%r language=%s", transcript[:140], detected_language)
            language_code = detected_language
            session.language_code = detected_language
            if session.stage == "greet":
                await prefetch_waitlist_identity(
                    deps=deps,
                    session=session,
                    airtable_client=airtable_client,
                )
            append_history(session, "user", transcript)

            timer.start("llm")
            plan, close_after_reply = await resolve_turn_plan(
                session=session,
                user_text=transcript,
                airtable_client=airtable_client,
            )
            reply_text, text_source = await generate_ra1_reply_text(
                deps=deps,
                client=sarvam_client,
                session=session,
                plan=plan,
            )
            timer.end("llm")
            append_history(session, "assistant", reply_text)
            reply_source = f"audio_{text_source}"

            try:
                timer.start("tts")
                tts_audio = await sarvam_synthesize_speech(
                    client=sarvam_client,
                    text=reply_text,
                    language_code=detected_language,
                )
                timer.end("tts")
                timer.start("media_upload")
                media_id = await upload_whatsapp_media(
                    logger=deps.logger,
                    client=meta_client,
                    filename="reply.mp3",
                    content_type="audio/mpeg",
                    media_bytes=tts_audio,
                )
                timer.end("media_upload")
                timer.start("send")
                await send_whatsapp_audio(
                    logger=deps.logger,
                    client=meta_client,
                    to=from_number,
                    media_id=media_id,
                )
                timer.end("send")
            except Exception as exc:
                timer.end("tts")
                deps.logger.warning("TTS failed for WhatsApp message: %s", exc)
                reply_source = f"{reply_source}_tts_fallback"
                timer.start("send")
                await send_whatsapp_text(
                    logger=deps.logger,
                    client=meta_client,
                    to=from_number,
                    body=reply_text,
                )
                timer.end("send")
        except Exception as exc:
            timer.end("stt")
            deps.logger.warning("STT/audio handling failed for WhatsApp message: %s", exc)
            reply_source = "audio_stt_fallback"
            timer.start("send")
            await send_whatsapp_text(
                logger=deps.logger,
                client=meta_client,
                to=from_number,
                body=stt_fallback_message(session.language_code),
            )
            timer.end("send")

        deps.logger.info("WA_LATENCY %s", timer.summary("audio", reply_source, language_code))
        if close_after_reply:
            deps.session_store().clear(from_number)
        return

    reply_text = fallback_response("", language_code)
    timer.start("send")
    await send_whatsapp_text(logger=deps.logger, client=meta_client, to=from_number, body=reply_text)
    timer.end("send")
    deps.logger.info("WA_LATENCY %s", timer.summary("unknown", "fallback", language_code))


def create_whatsapp_router(deps: WhatsAppDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/whatsapp/webhook")
    async def verify_whatsapp_webhook(request: Request):
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge", "")
        expected = whatsapp_verify_token()

        if mode == "subscribe" and token and expected and token == expected:
            deps.logger.info("WhatsApp webhook verified")
            return PlainTextResponse(challenge)

        deps.logger.warning("WhatsApp webhook verification failed: mode=%s token_present=%s", mode, bool(token))
        return PlainTextResponse("forbidden", status_code=403)

    @router.post("/whatsapp/webhook")
    async def receive_whatsapp_webhook(request: Request):
        try:
            payload = await request.json()
        except Exception:
            deps.logger.warning("WhatsApp webhook received invalid JSON")
            return {"status": "ignored"}

        messages = extract_whatsapp_messages(payload)
        if not messages:
            deps.logger.info("WhatsApp webhook contained no inbound messages")
            return {"status": "ok"}

        for message in messages:
            try:
                await handle_whatsapp_message(deps=deps, message=message)
            except Exception as exc:
                deps.logger.error("WhatsApp message handling failed: %s", exc, exc_info=True)

        return {"status": "ok"}

    return router
