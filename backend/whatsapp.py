from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from base64 import b64decode
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from .conversation import DIRECT_STT_FALLBACK, DirectSessionStore, direct_session_business, handle_direct_turn
from .fallbacks import fallback_response
from .llm_utils import normalize_language


FAST_ACK_MESSAGES = {
    "en-IN": "Got it, checking that now.",
    "hi-IN": "Theek hai, abhi check kar raha hoon.",
    "ml-IN": "Okay, ippol nokkatte.",
    "ta-IN": "Seri, ippo paarkiren.",
}

BACKGROUND_RECOVERY_MESSAGES = {
    "en-IN": "Someone from our team will follow up within 24 hours on WhatsApp.",
    "hi-IN": "Hamari team ka koi member 24 ghante mein aapko WhatsApp par follow up karega.",
    "ml-IN": "Njangalude team 24 manikoorinullil WhatsApp-il ningale follow up cheyyum.",
    "ta-IN": "Engal team 24 mani nerathirkul WhatsApp-il ungalai follow up seivargal.",
}

AUDIO_REPLY_TIMEOUT = "I got your voice note, but I'm taking too long to reply properly. Please send it as text or try once more."
MESSAGE_DEDUPE_TTL_SECONDS = 300
_RECENT_MESSAGE_IDS: dict[str, float] = {}


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


@dataclass
class WhatsAppDeps:
    logger: logging.Logger
    meta_client_getter: Any
    sarvam_client_getter: Any
    groq_client_getter: Any
    airtable_client_getter: Any
    direct_session_store_getter: Any

    def meta_client(self) -> httpx.AsyncClient:
        return self.meta_client_getter()

    def sarvam_client(self) -> httpx.AsyncClient:
        return self.sarvam_client_getter()

    def groq_client(self) -> httpx.AsyncClient:
        return self.groq_client_getter()

    def airtable_client(self) -> httpx.AsyncClient:
        return self.airtable_client_getter()

    def direct_session_store(self) -> DirectSessionStore:
        return self.direct_session_store_getter()


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


def inbound_message_id(message: dict) -> str:
    return (message.get("id") or "").strip()


def new_turn_id(message_id: str = "") -> str:
    if message_id:
        suffix = re.sub(r"[^A-Za-z0-9]+", "-", message_id)[-24:].strip("-")
        if suffix:
            return f"turn-{suffix}"
    return f"turn-{uuid.uuid4().hex[:12]}"


def target_language_for_tts(language_code: str | None) -> str:
    return normalize_language(language_code or os.getenv("WHATSAPP_DEFAULT_LANGUAGE", "en-IN"))


def fast_reply_timeout_seconds() -> float:
    raw = os.getenv("WHATSAPP_FAST_REPLY_TIMEOUT_MS", "1200")
    try:
        return max(int(raw), 0) / 1000
    except ValueError:
        return 1.2


def audio_conversation_timeout_seconds() -> float:
    raw = os.getenv("WHATSAPP_AUDIO_CONVERSATION_TIMEOUT_MS", "8000")
    try:
        return max(int(raw), 1) / 1000
    except ValueError:
        return 8.0


def get_fast_ack(language_code: str) -> str:
    normalized = normalize_language(language_code)
    return FAST_ACK_MESSAGES.get(normalized, FAST_ACK_MESSAGES["en-IN"])


def get_background_recovery(language_code: str) -> str:
    normalized = normalize_language(language_code)
    return BACKGROUND_RECOVERY_MESSAGES.get(normalized, BACKGROUND_RECOVERY_MESSAGES["en-IN"])


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


def should_process_message(message: dict) -> bool:
    message_id = (message.get("id") or "").strip()
    if not message_id:
        return True
    now = time.time()
    expired = [key for key, seen_at in _RECENT_MESSAGE_IDS.items() if now - seen_at > MESSAGE_DEDUPE_TTL_SECONDS]
    for key in expired:
        _RECENT_MESSAGE_IDS.pop(key, None)
    if message_id in _RECENT_MESSAGE_IDS:
        return False
    _RECENT_MESSAGE_IDS[message_id] = now
    return True


def default_tts_speaker() -> str:
    return os.getenv("SARVAM_TTS_SPEAKER", "shubh")


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


async def safe_send_whatsapp_text(*, logger: Any, client: httpx.AsyncClient, to: str, body: str) -> bool:
    try:
        await send_whatsapp_text(logger=logger, client=client, to=to, body=body)
        return True
    except Exception as exc:
        logger.warning("WhatsApp text send skipped/failed: %s: %s", type(exc).__name__, exc)
        return False


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


async def safe_send_whatsapp_audio(*, logger: Any, client: httpx.AsyncClient, to: str, media_id: str) -> bool:
    try:
        await send_whatsapp_audio(logger=logger, client=client, to=to, media_id=media_id)
        return True
    except Exception as exc:
        logger.warning("WhatsApp audio send skipped/failed: %s: %s", type(exc).__name__, exc)
        return False


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


async def sarvam_transcribe_audio(
    *,
    client: httpx.AsyncClient,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
) -> tuple[str, str]:
    response = await client.post(
        "https://api.sarvam.ai/speech-to-text",
        headers={"api-subscription-key": os.getenv("SARVAM_API_KEY", "")},
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
            "api-subscription-key": os.getenv("SARVAM_API_KEY", ""),
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


def prepare_voice_reply_text(reply: str) -> str:
    cleaned = " ".join((reply or "").split())
    if not cleaned:
        return ""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    spoken = " ".join(sentences[:2]) if sentences else cleaned
    return spoken[:260].strip()


async def send_hybrid_text_reply(
    *,
    deps: WhatsAppDeps,
    meta_client: httpx.AsyncClient,
    llm_client: httpx.AsyncClient,
    airtable_client: httpx.AsyncClient,
    session: Any,
    from_number: str,
    user_text: str,
    language_code: str,
    timer: StageTimer,
    turn_id: str = "",
    message_id: str = "",
) -> None:
    turn_id = turn_id or new_turn_id(message_id)
    turn_task = asyncio.create_task(
        handle_direct_turn(
            logger=deps.logger,
            llm_client=llm_client,
            airtable_client=airtable_client,
            session=session,
            user_text=user_text,
            language_code=language_code,
        )
    )
    try:
        timer.start("conversation")
        result = await asyncio.wait_for(asyncio.shield(turn_task), timeout=fast_reply_timeout_seconds())
        timer.end("conversation")
    except asyncio.TimeoutError:
        timer.end("conversation")
        ack = get_fast_ack(language_code)
        timer.start("send")
        ack_sent = await safe_send_whatsapp_text(logger=deps.logger, client=meta_client, to=from_number, body=ack)
        timer.end("send")
        deps.logger.info(
            "WA_LATENCY %s",
            {
                **timer.summary("text", "fast_ack", language_code),
                "hybrid": True,
                "ack_sent": ack_sent,
                "final_sent": False,
                "turn_id": turn_id,
                "message_id": message_id,
            },
        )
        create_tracked_background_task(
            deps,
            finish_background_text_reply(
                deps=deps,
                meta_client=meta_client,
                turn_task=turn_task,
                session=session,
                from_number=from_number,
                language_code=language_code,
                turn_id=turn_id,
                message_id=message_id,
            ),
            turn_id=turn_id,
            message_id=message_id,
        )
        return

    timer.start("send")
    final_sent = await safe_send_whatsapp_text(logger=deps.logger, client=meta_client, to=from_number, body=result.reply)
    timer.end("send")
    log_agent_summary(
        deps=deps,
        source=result.source,
        airtable_status=result.airtable_status,
        session=session,
        turn_id=turn_id,
        message_id=message_id,
        final_sent=final_sent,
    )
    deps.logger.info(
        "WA_LATENCY %s",
        {
            **timer.summary("text", result.source, language_code),
            "hybrid": False,
            "final_sent": final_sent,
            "turn_id": turn_id,
            "message_id": message_id,
        },
    )


def create_tracked_background_task(
    deps: WhatsAppDeps,
    coroutine,
    *,
    turn_id: str,
    message_id: str,
) -> asyncio.Task:
    async def runner():
        deps.logger.info("WA_BACKGROUND_START turn_id=%s message_id=%s", turn_id, message_id)
        try:
            await coroutine
        except Exception:
            deps.logger.exception("WA_BACKGROUND_CRASH turn_id=%s message_id=%s", turn_id, message_id)

    return asyncio.create_task(runner())


async def finish_background_text_reply(
    *,
    deps: WhatsAppDeps,
    meta_client: httpx.AsyncClient,
    turn_task: asyncio.Task,
    session: Any,
    from_number: str,
    language_code: str,
    turn_id: str = "",
    message_id: str = "",
) -> None:
    started = time.time()
    try:
        result = await turn_task
        final_sent = await safe_send_whatsapp_text(logger=deps.logger, client=meta_client, to=from_number, body=result.reply)
        log_agent_summary(
            deps=deps,
            source=result.source,
            airtable_status=result.airtable_status,
            session=session,
            turn_id=turn_id,
            message_id=message_id,
            final_sent=final_sent,
        )
        deps.logger.info(
            "WA_BACKGROUND source=%s language=%s background_ms=%s turn_id=%s message_id=%s final_sent=%s",
            result.source,
            language_code,
            int((time.time() - started) * 1000),
            turn_id,
            message_id,
            final_sent,
        )
    except Exception as exc:
        deps.logger.exception("Background reply failed turn_id=%s message_id=%s", turn_id, message_id)
        recovery_sent = await safe_send_whatsapp_text(
            logger=deps.logger,
            client=meta_client,
            to=from_number,
            body=get_background_recovery(language_code),
        )
        deps.logger.info(
            "WA_BACKGROUND_RECOVERY turn_id=%s message_id=%s recovery_sent=%s error=%s",
            turn_id,
            message_id,
            recovery_sent,
            type(exc).__name__,
        )


def log_agent_summary(
    *,
    deps: WhatsAppDeps,
    source: str,
    airtable_status: str,
    session: Any,
    turn_id: str = "",
    message_id: str = "",
    final_sent: bool | None = None,
) -> None:
    deps.logger.info(
        "WA_AGENT source=%s airtable_status=%s known_name=%s known_business_present=%s history_turns=%s turn_id=%s message_id=%s final_sent=%s",
        source,
        airtable_status,
        bool(getattr(session, "name", "")),
        bool(direct_session_business(session)),
        len(session.history),
        turn_id,
        message_id,
        final_sent,
    )


async def handle_whatsapp_message(*, deps: WhatsAppDeps, message: dict) -> None:
    from_number = message.get("from")
    if not from_number:
        deps.logger.info("Ignoring WhatsApp message without sender: %s", message)
        return
    message_id = inbound_message_id(message)
    if not should_process_message(message):
        deps.logger.info("Ignoring duplicate WhatsApp message id=%s", message.get("id"))
        return
    turn_id = new_turn_id(message_id)

    timer = StageTimer()
    meta_client = deps.meta_client()
    sarvam_client = deps.sarvam_client()
    groq_client = deps.groq_client()
    airtable_client = deps.airtable_client()
    direct_session = deps.direct_session_store().get(from_number)
    language_code = normalize_language(os.getenv("WHATSAPP_DEFAULT_LANGUAGE", "en-IN"))
    text_body = message_text_body(message)
    audio_id = message_audio_id(message)

    if text_body:
        language_code = detect_text_language(text_body)
        await send_hybrid_text_reply(
            deps=deps,
            meta_client=meta_client,
            llm_client=groq_client,
            airtable_client=airtable_client,
            session=direct_session,
            from_number=from_number,
            user_text=text_body,
            language_code=language_code,
            timer=timer,
            turn_id=turn_id,
            message_id=message_id,
        )
        return

    if audio_id:
        reply_source = "audio"
        conversation_result = None
        final_sent = False
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

            timer.start("conversation")
            try:
                conversation_result = await asyncio.wait_for(
                    handle_direct_turn(
                        logger=deps.logger,
                        llm_client=groq_client,
                        airtable_client=airtable_client,
                        session=direct_session,
                        user_text=transcript,
                        language_code=detected_language,
                    ),
                    timeout=audio_conversation_timeout_seconds(),
                )
                reply_text = conversation_result.reply
                reply_source = f"audio_{conversation_result.source}"
            except asyncio.TimeoutError:
                deps.logger.warning("Audio conversation timed out after STT transcript=%r", transcript[:140])
                reply_text = AUDIO_REPLY_TIMEOUT
                reply_source = "audio_timeout_fallback"
            timer.end("conversation")

            try:
                if reply_source == "audio_timeout_fallback":
                    timer.start("send")
                    final_sent = await safe_send_whatsapp_text(
                        logger=deps.logger,
                        client=meta_client,
                        to=from_number,
                        body=reply_text,
                    )
                    timer.end("send")
                else:
                    reply_text = prepare_voice_reply_text(reply_text)
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
                    final_sent = await safe_send_whatsapp_audio(
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
                final_sent = await safe_send_whatsapp_text(
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
            final_sent = await safe_send_whatsapp_text(
                logger=deps.logger,
                client=meta_client,
                to=from_number,
                body=DIRECT_STT_FALLBACK,
            )
            timer.end("send")

        deps.logger.info(
            "WA_AGENT source=%s airtable_status=%s known_name=%s known_business_present=%s history_turns=%s turn_id=%s message_id=%s final_sent=%s",
            reply_source,
            conversation_result.airtable_status if conversation_result else "not_checked",
            bool(getattr(direct_session, "name", "")),
            bool(direct_session_business(direct_session)),
            len(direct_session.history),
            turn_id,
            message_id,
            final_sent,
        )
        deps.logger.info(
            "WA_LATENCY %s",
            {
                **timer.summary("audio", reply_source, language_code),
                "turn_id": turn_id,
                "message_id": message_id,
                "final_sent": final_sent,
            },
        )
        return

    reply_text = fallback_response("", language_code)
    timer.start("send")
    final_sent = await safe_send_whatsapp_text(logger=deps.logger, client=meta_client, to=from_number, body=reply_text)
    timer.end("send")
    deps.logger.info(
        "WA_LATENCY %s",
        {
            **timer.summary("unknown", "fallback", language_code),
            "turn_id": turn_id,
            "message_id": message_id,
            "final_sent": final_sent,
        },
    )


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
