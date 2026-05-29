from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request
from groq import AsyncGroq
from pipecat.frames.frames import (
    EndFrame,
    Frame,
    LLMContextFrame,
    LLMTextFrame,
    StartFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport

from .voice_agent import (
    RA1_CALL_SYSTEM_PROMPT,
)

logger = logging.getLogger("upthrust.call_router")

_active_calls: dict[str, PipelineRunner] = {}

CLOSING_TEXT = "Thanks for your time. We'll follow up on WhatsApp within 24 hours. Have a great day."

LANGUAGE_NAMES = {
    "en-IN": "English",
    "hi-IN": "Hindi",
    "ml-IN": "Malayalam",
    "ta-IN": "Tamil",
}

LANGUAGE_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\benglish\b", re.I), "en-IN"),
    (re.compile(r"\ben\b", re.I), "en-IN"),
    (re.compile(r"\bhindi\b", re.I), "hi-IN"),
    (re.compile(r"\bhi\b", re.I), "hi-IN"),
    (re.compile(r"हिन्दी"), "hi-IN"),
    (re.compile(r"\bmalayalam\b", re.I), "ml-IN"),
    (re.compile(r"\bml\b", re.I), "ml-IN"),
    (re.compile(r"മലയാളം"), "ml-IN"),
    (re.compile(r"\btamil\b", re.I), "ta-IN"),
    (re.compile(r"\bta\b", re.I), "ta-IN"),
    (re.compile(r"தமிழ்"), "ta-IN"),
]


@dataclass
class CallState:
    language: str | None = None
    business: str | None = None
    support_issue: str | None = None
    channel: str | None = None
    turn_count: int = 0
    value_dropped: bool = False
    hangup_requested: bool = False


EXTRACT_PROMPT = """Extract business information from this user message.
Return JSON with these keys (set to null if not present):

- business: what kind of business they run (e.g. "auto garage", "pharmacy", "restaurant", "bakery", "workshop", "clinic")
- support_issue: what customer support issues they deal with (e.g. "delivery tracking", "order complaints", "repair status")
- channel: how customers contact them ("phone", "whatsapp", "email", "website", or null)

User: "{text}"""


async def extract_facts(text: str, client: AsyncGroq) -> dict[str, Any]:
    try:
        resp = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": EXTRACT_PROMPT.format(text=text)}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {}


def detect_language(text: str) -> str | None:
    for pattern, code in LANGUAGE_KEYWORDS:
        if pattern.search(text):
            return code
    return None


def should_hangup(text: str, state: CallState) -> bool:
    if state.hangup_requested:
        return True
    if not all([state.business, state.support_issue, state.channel]):
        return False
    lowered = text.lower().strip()
    terminal = any(
        lowered.endswith(p) for p in ["bye", "goodbye", "thanks", "thank you", "that's all"]
    )
    return terminal and "?" not in lowered


def pick_move(state: CallState, just_detected_field: str | None = None) -> tuple[str, str | None]:
    if state.hangup_requested:
        return ("hard_close", None)

    missing = [f for f in ["business", "support_issue", "channel"] if not getattr(state, f)]

    if just_detected_field and state.turn_count > 1:
        return ("react", just_detected_field)

    if missing:
        field = missing[0]
        return ("ask_field", field)

    if not state.value_dropped:
        return ("drop_value", None)

    return ("soft_close", None)


def build_move_instruction(move: str, field: str | None, state: CallState) -> str:
    field_descriptions = {
        "business": "what kind of business they run",
        "support_issue": "what customer support issues they deal with most",
        "channel": "how customers usually contact them",
    }

    if move == "ask_field" and field:
        desc = field_descriptions.get(field, field)
        return f"Current goal: Ask {desc}.\nKeep the reply under 15 words. Ask one natural follow-up question."

    if move == "react" and field:
        desc = field_descriptions.get(field, field)
        return f"Current goal: Acknowledge what they shared about {desc}, then ask one follow-up question about it.\nKeep it under 20 words."

    if move == "drop_value":
        parts = []
        if state.business:
            parts.append(f"they run a {state.business}")
        if state.support_issue:
            parts.append(f"handle {state.support_issue} questions")
        if state.channel:
            parts.append(f"use {state.channel}")
        context = ", ".join(parts) if parts else "their situation"
        return (
            f"Current goal: In a single sentence, briefly summarize what you learned "
            f"({context}) and explain how Buoyancy can automate their specific support needs. "
            "End by offering a WhatsApp follow-up within 24 hours. Do not ask questions."
        )

    if move == "soft_close":
        return "Current goal: Offer a WhatsApp follow-up within 24 hours and close warmly.\nKeep it under 15 words."

    return ""


class SilenceHandler(FrameProcessor):
    def __init__(self, timeout: float = 6.0) -> None:
        super().__init__()
        self._timeout = timeout
        self._task: asyncio.Task | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            self._reset_timer()
        await self.push_frame(frame, direction)

    def _reset_timer(self) -> None:
        if self._task:
            self._task.cancel()
        self._task = self.create_task(self._silence_loop())

    async def _silence_loop(self) -> None:
        await asyncio.sleep(self._timeout)
        await self.push_frame(TextFrame("Are you still there?"))
        await asyncio.sleep(self._timeout)
        await self.push_frame(EndFrame())


class CallContextBuilder(FrameProcessor):
    def __init__(self, groq_client: AsyncGroq) -> None:
        super().__init__()
        self._state = CallState()
        self._greeted = False
        self._groq_client = groq_client

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            logger.info("CallContextBuilder received StartFrame (greeted=%s)", self._greeted)
            if not self._greeted:
                self._greeted = True
                await self.push_frame(TextFrame(
                    "Hi, you've reached Buoyancy Labs. Which language would you like to continue in?"
                ))
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame):
            text = frame.text.strip()
            self._state.turn_count += 1

            if self._state.hangup_requested:
                await self.push_frame(frame, direction)
                return

            if not self._state.language:
                detected = detect_language(text)
                if detected:
                    self._state.language = detected

            missing = [f for f in ["business", "support_issue", "channel"] if not getattr(self._state, f)]
            just_detected = None
            if missing:
                facts = await extract_facts(text, self._groq_client)
                for field in missing:
                    val = facts.get(field)
                    if val and isinstance(val, str):
                        setattr(self._state, field, val)
                        if not just_detected:
                            just_detected = field

            if should_hangup(text, self._state):
                self._state.hangup_requested = True
                await self.push_frame(TextFrame(CLOSING_TEXT))
                self.create_task(self._end_after_delay())
                await self.push_frame(frame, direction)
                return

            move, field = pick_move(self._state, just_detected)
            instruction = build_move_instruction(move, field, self._state)

            context_lines = [RA1_CALL_SYSTEM_PROMPT]

            facts = []
            if self._state.language:
                facts.append(f"- Language: {LANGUAGE_NAMES.get(self._state.language, self._state.language)}")
            if self._state.business:
                facts.append(f"- Business: {self._state.business}")
            if self._state.support_issue:
                facts.append(f"- Support issue: {self._state.support_issue}")
            if self._state.channel:
                facts.append(f"- Channel: {self._state.channel}")

            if facts:
                context_lines.append("Known facts:\n" + "\n".join(facts))

            context_lines.append(f"Latest caller: \"{text}\"")
            if instruction:
                context_lines.append(instruction)

            context = LLMContext(
                messages=[{"role": "system", "content": "\n\n".join(context_lines)}]
            )
            await self.push_frame(LLMContextFrame(context))

        await self.push_frame(frame, direction)

    async def _end_after_delay(self) -> None:
        await asyncio.sleep(3)
        if self.pipeline_task:
            await self.pipeline_task.queue_frame(EndFrame())

    @property
    def state(self) -> CallState:
        return self._state


class CallContextUpdater(FrameProcessor):
    def __init__(self, context: LLMContext) -> None:
        super().__init__()
        self._context = context

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            logger.info("CallContextUpdater received StartFrame")
        if isinstance(frame, LLMTextFrame):
            self._context.add_message({"role": "assistant", "content": frame.text})
        await self.push_frame(frame, direction)


@dataclass
class CallDeps:
    logger: logging.Logger
    airtable_client_getter: Any = None
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_url: str = ""

    def __post_init__(self):
        self.livekit_api_key = os.getenv("LIVEKIT_API_KEY", "")
        self.livekit_api_secret = os.getenv("LIVEKIT_API_SECRET", "")
        self.livekit_url = os.getenv("LIVEKIT_URL", "")

    def airtable_client(self):
        if self.airtable_client_getter:
            return self.airtable_client_getter()
        return None


async def run_voice_pipeline(
    room_name: str,
    livekit_url: str,
    livekit_api_key: str,
    livekit_api_secret: str,
    token: str | None = None,
) -> None:
    from pipecat.runner.livekit import generate_token

    sarvam_api_key = os.getenv("SARVAM_API_KEY", "")
    groq_api_key = os.getenv("GROQ_API_KEY", "")

    if not sarvam_api_key:
        logger.error("SARVAM_API_KEY not set")
        return
    if not groq_api_key:
        logger.error("GROQ_API_KEY not set")
        return

    if token is None:
        token = generate_token(room_name, "ra1-agent", livekit_api_key, livekit_api_secret)

    groq_client = AsyncGroq(api_key=groq_api_key)

    transport = LiveKitTransport(
        url=livekit_url,
        token=token,
        room_name=room_name,
        params=LiveKitParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
        ),
    )

    stt = SarvamSTTService(
        api_key=sarvam_api_key,
        mode=os.getenv("VOICE_STT_MODE", "codemix"),
        settings=SarvamSTTService.Settings(
            model=os.getenv("VOICE_STT_MODEL", "saaras:v3"),
        ),
    )

    llm = GroqLLMService(
        api_key=groq_api_key,
        base_url="https://api.groq.com/openai/v1",
        settings=GroqLLMService.Settings(
            model=os.getenv("VOICE_LLM_MODEL", "llama-3.3-70b-versatile"),
            temperature=0.7,
            max_tokens=150,
        ),
    )

    tts = SarvamTTSService(
        api_key=sarvam_api_key,
        sample_rate=24000,
        settings=SarvamTTSService.Settings(
            model=os.getenv("VOICE_TTS_MODEL", "bulbul:v3"),
            voice=os.getenv("VOICE_TTS_VOICE", "shubh"),
        ),
    )

    context = LLMContext(
        messages=[{"role": "system", "content": RA1_CALL_SYSTEM_PROMPT}]
    )
    context_builder = CallContextBuilder(groq_client)
    context_updater = CallContextUpdater(context)

    silence_handler = SilenceHandler()
    pipeline = Pipeline([
        transport.input(),
        stt,
        silence_handler,
        context_builder,
        llm,
        context_updater,
        tts,
        transport.output(),
    ])

    task = PipelineTask(pipeline)
    runner = PipelineRunner()

    _active_calls[room_name] = runner
    try:
        await runner.run(task)
    finally:
        _active_calls.pop(room_name, None)
        logger.info("Voice pipeline ended for room %s", room_name)


def create_call_router(deps: CallDeps) -> APIRouter:
    router = APIRouter(prefix="/call")

    @router.post("/incoming")
    async def call_incoming(request: Request):
        try:
            payload = await request.json()
        except Exception:
            logger.warning("Call incoming webhook received invalid JSON")
            return {"status": "ignored"}

        caller_phone = (
            payload.get("from")
            or payload.get("caller")
            or ""
        )
        if not caller_phone:
            logger.info("Call incoming without caller phone: %s", payload)
            caller_phone = "unknown"

        call_id = (
            payload.get("call_id")
            or payload.get("id")
            or "unknown"
        )
        deps.logger.info(
            "CALL_INCOMING call_id=%s from=%s",
            call_id,
            caller_phone,
        )
        return {"status": "ringing", "call_id": call_id}

    @router.post("/answered")
    async def call_answered(request: Request, background_tasks: BackgroundTasks):
        try:
            payload = await request.json()
        except Exception:
            logger.warning("Call answered webhook received invalid JSON")
            return {"status": "ignored"}

        caller_phone = (
            payload.get("from")
            or payload.get("caller")
            or ""
        )
        call_id = (
            payload.get("call_id")
            or payload.get("id")
            or "unknown"
        )
        room_name = payload.get("room", f"call-{call_id}")

        lk_url = deps.livekit_url
        lk_key = deps.livekit_api_key
        lk_secret = deps.livekit_api_secret

        if not lk_url or not lk_key or not lk_secret:
            deps.logger.warning(
                "LiveKit not configured — pipecat pipeline will not start. "
                "Set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET"
            )
            return {"status": "connected", "call_id": call_id, "room": room_name}

        deps.logger.info(
            "CALL_ANSWERED call_id=%s from=%s room=%s — starting pipecat pipeline",
            call_id,
            caller_phone,
            room_name,
        )

        background_tasks.add_task(
            run_voice_pipeline,
            room_name,
            lk_url,
            lk_key,
            lk_secret,
        )

        return {
            "status": "connected",
            "call_id": call_id,
            "room": room_name,
        }

    @router.post("/ended")
    async def call_ended(request: Request):
        try:
            payload = await request.json()
        except Exception:
            logger.warning("Call ended webhook received invalid JSON")
            return {"status": "ignored"}

        caller_phone = (
            payload.get("from")
            or payload.get("caller")
            or ""
        )
        call_id = (
            payload.get("call_id")
            or payload.get("id")
            or "unknown"
        )
        duration_sec = payload.get("duration_sec", 0)
        deps.logger.info(
            "CALL_ENDED call_id=%s from=%s duration_sec=%s",
            call_id,
            caller_phone,
            duration_sec,
        )
        return {"status": "ok", "call_id": call_id}

    @router.get("/status/{call_id}")
    async def call_status(call_id: str):
        return {"call_id": call_id, "status": "unknown"}

    @router.post("/dtmf")
    async def call_dtmf(request: Request):
        try:
            payload = await request.json()
        except Exception:
            return {"status": "ignored"}
        deps.logger.info("CALL_DTMF call_id=%s digit=%s", payload.get("call_id"), payload.get("digit"))
        return {"status": "ok"}

    @router.post("/livekit/webhook")
    async def livekit_webhook(request: Request, background_tasks: BackgroundTasks):
        try:
            payload = await request.json()
        except Exception:
            logger.warning("LiveKit webhook received invalid JSON")
            return {"status": "ignored"}

        event = payload.get("event", "")
        room_name = ""
        if payload.get("room"):
            room_name = payload["room"].get("name", "")
        if not room_name:
            return {"status": "ignored"}

        lk_url = deps.livekit_url
        lk_key = deps.livekit_api_key
        lk_secret = deps.livekit_api_secret

        deps.logger.info(
            "LIVEKIT_WEBHOOK event=%s room=%s",
            event,
            room_name,
        )

        if event in ("room.started", "participant_joined") and lk_url and lk_key and lk_secret:
            deps.logger.info(
                "LIVEKIT_WEBHOOK starting pipeline for room %s",
                room_name,
            )
            background_tasks.add_task(
                run_voice_pipeline,
                room_name,
                lk_url,
                lk_key,
                lk_secret,
            )

        return {"status": "ok"}

    return router
