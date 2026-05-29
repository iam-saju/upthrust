from __future__ import annotations

import logging
from typing import Any

import httpx

from .airtable import add_waitlist_caller, find_waitlist_caller
from .voice_agent import (
    build_call_messages,
    cap_reply_sentences,
    get_closing,
    get_fallback,
    get_greeting,
    is_closing,
    validate_user_facing_reply,
    sanitize_user_facing_reply,
)
from .voice_session import (
    CallSession,
    CallSessionStore,
    append_history,
    is_farewell,
    is_greeting,
    is_ready_to_write,
    update_profile_from_text,
)

logger = logging.getLogger("upthrust.voice_processor")


class RA1CallPreProcessor:
    def __init__(
        self,
        session: CallSession,
        session_store: CallSessionStore,
        airtable_client: httpx.AsyncClient | None = None,
    ):
        self._session = session
        self._session_store = session_store
        self._airtable_client = airtable_client

    async def pre_process(self, user_text: str) -> tuple[str | None, str | None]:
        text = " ".join((user_text or "").strip().split())
        if not text:
            return None, get_fallback(self._session.language_code)

        if not self._session.airtable_checked and self._airtable_client is not None:
            try:
                await self._prefetch_identity()
            except Exception as exc:
                logger.warning("Call Airtable prefetch failed: %s", exc)

        if is_greeting(text) and not self._session.profile.name:
            if not self._session.known_caller:
                reply = get_greeting(self._session.language_code)
                append_history(self._session, "user", text)
                append_history(self._session, "assistant", reply)
                return None, reply

        if is_farewell(text):
            reply = get_closing(self._session.language_code)
            append_history(self._session, "user", text)
            append_history(self._session, "assistant", reply)
            return None, reply

        update_profile_from_text(self._session, text)
        append_history(self._session, "user", text)
        messages = build_call_messages(self._session, text)
        return messages, None

    async def _prefetch_identity(self) -> None:
        if self._airtable_client is None:
            return
        record = await find_waitlist_caller(
            client=self._airtable_client,
            phone=self._session.profile.phone,
        )
        self._session.airtable_checked = True
        if record:
            self._session.known_caller = True
            self._session.known_record = {key: str(value) for key, value in record.items()}
        else:
            self._session.known_caller = False


class RA1CallPostProcessor:
    def __init__(
        self,
        session: CallSession,
        airtable_client: httpx.AsyncClient | None = None,
    ):
        self._session = session
        self._airtable_client = airtable_client

    async def post_process(self, llm_reply: str) -> str:
        if not validate_user_facing_reply(llm_reply):
            reply = get_fallback(self._session.language_code)
        else:
            reply = sanitize_user_facing_reply(cap_reply_sentences(llm_reply))
            if not reply:
                reply = get_fallback(self._session.language_code)

        append_history(self._session, "assistant", reply)

        if is_ready_to_write(self._session) and self._airtable_client is not None:
            try:
                await add_waitlist_caller(client=self._airtable_client, session=self._session)
                self._session.waitlist_added = True
            except Exception as exc:
                logger.warning("Call Airtable write failed: %s", exc)

        return reply

    async def on_call_end(self) -> None:
        if is_ready_to_write(self._session) and self._airtable_client is not None:
            try:
                await add_waitlist_caller(client=self._airtable_client, session=self._session)
                self._session.waitlist_added = True
            except Exception as exc:
                logger.warning("Call-end Airtable write failed: %s", exc)
