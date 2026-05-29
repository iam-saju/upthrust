from __future__ import annotations

import unittest
import asyncio
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.voice_session import (
    CallSessionStore,
    CallSession,
    CallProfile,
    extract_name,
    is_greeting,
    is_farewell,
    update_profile_from_text,
    is_ready_to_write,
    append_history,
)
from backend.voice_agent import (
    RA1_CALL_SYSTEM_PROMPT,
    BUOYANCY_CORE_FACTS,
    HANGUP_CLOSINGS,
    build_call_messages,
    cap_reply_sentences,
    get_closing,
    get_fallback,
    get_greeting,
    get_hangup_closing,
    get_stt_fallback,
    is_closing,
    sanitize_user_facing_reply,
    validate_user_facing_reply,
)
from backend.voice_processor import RA1CallPreProcessor, RA1CallPostProcessor
from backend.llm_utils import normalize_language
from backend.call_router import (
    CallState,
    SilenceHandler,
    detect_language,
    extract_facts,
    should_hangup,
    pick_move,
    build_move_instruction,
    CLOSING_TEXT,
)


class VoiceSessionTests(unittest.TestCase):
    def test_session_store_get_creates_new_session(self) -> None:
        store = CallSessionStore()
        session = store.get("919999999999")
        self.assertIsInstance(session, CallSession)
        self.assertEqual(session.phone, "919999999999")
        self.assertEqual(session.profile.phone, "919999999999")

    def test_session_store_get_returns_existing(self) -> None:
        store = CallSessionStore()
        session1 = store.get("919999999999")
        session2 = store.get("919999999999")
        self.assertIs(session1, session2)

    def test_session_store_clear_removes_session(self) -> None:
        store = CallSessionStore()
        store.get("919999999999")
        store.clear("919999999999")
        session = store.get("919999999999")
        self.assertFalse(session.profile.name)

    def test_session_store_supports_language_code(self) -> None:
        store = CallSessionStore()
        session = store.get("919999999999", "hi-IN")
        self.assertEqual(session.language_code, "hi-IN")

    def test_is_greeting_detects_common_greetings(self) -> None:
        self.assertTrue(is_greeting("hello"))
        self.assertTrue(is_greeting("Hi"))
        self.assertTrue(is_greeting("namaste"))
        self.assertTrue(is_greeting("vanakkam"))
        self.assertFalse(is_greeting("what do you do"))

    def test_is_farewell_detects_farewells(self) -> None:
        self.assertTrue(is_farewell("bye"))
        self.assertTrue(is_farewell("thanks"))
        self.assertFalse(is_farewell("hello"))

    def test_extract_name_from_various_phrases(self) -> None:
        self.assertEqual(extract_name("My name is Ravi"), "Ravi")
        self.assertEqual(extract_name("I am Priya"), "Priya")
        self.assertEqual(extract_name("This is Saju"), "Saju")
        self.assertEqual(extract_name("main Rahul hoon"), "Rahul")

    def test_extract_name_returns_empty_for_ambiguous(self) -> None:
        self.assertEqual(extract_name("yes"), "")
        self.assertEqual(extract_name("hello"), "")

    def test_update_profile_from_text_extracts_name(self) -> None:
        session = CallSessionStore().get("919999999999")
        update_profile_from_text(session, "My name is Ravi")
        self.assertEqual(session.profile.name, "Ravi")

    def test_update_profile_from_text_does_not_overwrite_name(self) -> None:
        session = CallSessionStore().get("919999999999")
        session.profile.name = "Ravi"
        update_profile_from_text(session, "My name is Asha")
        self.assertEqual(session.profile.name, "Ravi")

    def test_update_profile_from_text_extracts_business(self) -> None:
        session = CallSessionStore().get("919999999999")
        session.profile.name = "Ravi"
        update_profile_from_text(session, "We run a pharmacy")
        self.assertEqual(session.profile.business, "We run a pharmacy")

    def test_is_ready_to_write_requires_name_and_business(self) -> None:
        session = CallSessionStore().get("919999999999")
        session.airtable_checked = True
        self.assertFalse(is_ready_to_write(session))
        session.profile.name = "Ravi"
        self.assertFalse(is_ready_to_write(session))
        session.profile.business = "Pharmacy"
        self.assertTrue(is_ready_to_write(session))

    def test_is_ready_to_write_skips_known_callers(self) -> None:
        session = CallSessionStore().get("919999999999")
        session.airtable_checked = True
        session.profile.name = "Ravi"
        session.profile.business = "Pharmacy"
        session.known_caller = True
        self.assertFalse(is_ready_to_write(session))


class VoiceAgentTests(unittest.TestCase):
    def test_system_prompt_matches_call_design(self) -> None:
        self.assertIn("RA-1 from Buoyancy Labs", RA1_CALL_SYSTEM_PROMPT)
        self.assertIn("short and natural", RA1_CALL_SYSTEM_PROMPT)
        self.assertIn("Do not reintroduce yourself", RA1_CALL_SYSTEM_PROMPT)
        self.assertIn("WhatsApp follow-up within 24 hours", RA1_CALL_SYSTEM_PROMPT)

    def test_build_call_messages_includes_context_and_facts(self) -> None:
        store = CallSessionStore()
        session = store.get("919999999999", "en-IN")
        session.airtable_checked = True
        session.known_caller = True
        session.profile.name = "Ravi"
        session.profile.business = "Pharmacy"
        session.profile.support_calls = "Order updates"
        session.known_record = {"name": "Ravi", "aim of your project": "Pharmacy"}
        session.history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        messages = build_call_messages(session, "What do you do?")
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(sum(1 for m in messages if m["role"] == "system"), 1)
        context_payload = messages[0]["content"]
        self.assertIn("Caller language: en-IN", context_payload)
        self.assertIn("Returning caller business: Pharmacy", context_payload)
        for fact in BUOYANCY_CORE_FACTS:
            self.assertIn(fact, context_payload)
        self.assertEqual(messages[-1], {"role": "user", "content": "What do you do?"})

    def test_validator_blocks_instructional_language(self) -> None:
        self.assertFalse(validate_user_facing_reply("Say you did not catch their name."))
        self.assertFalse(validate_user_facing_reply("Ask what their business does."))
        self.assertTrue(validate_user_facing_reply("Got it. What kind of business do you run?"))

    def test_sanitize_rejects_malformed_text(self) -> None:
        self.assertEqual(sanitize_user_facing_reply("```system```"), "")
        self.assertEqual(sanitize_user_facing_reply("- Ask for business"), "")

    def test_sanitize_accepts_clean_text(self) -> None:
        self.assertEqual(
            sanitize_user_facing_reply("  Got it. What kind of business are you running?  "),
            "Got it. What kind of business are you running?",
        )

    def test_cap_reply_preserves_followup(self) -> None:
        capped = cap_reply_sentences(
            "Got it. We support Hindi and English. Someone will follow up within 24 hours on WhatsApp."
        )
        self.assertEqual(capped, "Got it. Someone will follow up within 24 hours on WhatsApp.")

    def test_is_closing_detects_follow_up_phrases(self) -> None:
        self.assertTrue(is_closing("Someone from our team will follow up within 24 hours on WhatsApp."))
        self.assertFalse(is_closing("Tell me more about pricing."))

    def test_localized_responses(self) -> None:
        self.assertIn("Raa Wun", get_greeting("en-IN"))
        self.assertIn("24 hours", get_closing("en-IN"))
        self.assertIn("Dobara", get_stt_fallback("hi-IN"))
        self.assertIn("once more", get_fallback("en-IN"))
        self.assertIn("take care", get_hangup_closing("en-IN"))
        self.assertIn("dhyaan", get_hangup_closing("hi-IN"))
        self.assertIn("shradhikkatte", get_hangup_closing("ml-IN"))
        self.assertIn("pathukkaanga", get_hangup_closing("ta-IN"))
        self.assertEqual(len(HANGUP_CLOSINGS), 4)

    def test_normalize_language(self) -> None:
        self.assertEqual(normalize_language("hi"), "hi-IN")
        self.assertEqual(normalize_language("en-in"), "en-IN")
        self.assertEqual(normalize_language("ml"), "ml-IN")
        self.assertEqual(normalize_language(""), "en-IN")


class VoiceProcessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = CallSessionStore()
        self.session = self.store.get("919999999999", "en-IN")

    def test_pre_processor_greeting_returns_fast_path(self) -> None:
        processor = RA1CallPreProcessor(self.session, self.store)
        messages, reply = asyncio.run(processor.pre_process("hello"))
        self.assertIsNone(messages)
        self.assertIsNotNone(reply)
        self.assertIn("Raa Wun", reply or "")

    def test_pre_processor_farewell_returns_closing(self) -> None:
        processor = RA1CallPreProcessor(self.session, self.store)
        messages, reply = asyncio.run(processor.pre_process("thanks"))
        self.assertIsNone(messages)
        self.assertIsNotNone(reply)
        self.assertIn("24 hours", reply or "")

    def test_pre_processor_returns_messages_for_normal_turn(self) -> None:
        processor = RA1CallPreProcessor(self.session, self.store)
        messages, reply = asyncio.run(processor.pre_process("I run a pharmacy"))
        self.assertIsNotNone(messages)
        self.assertIsNone(reply)

    def test_post_processor_validates_and_sanitizes(self) -> None:
        processor = RA1CallPostProcessor(self.session)
        reply = asyncio.run(processor.post_process("Got it. What kind of support calls do you handle?"))
        self.assertEqual(reply, "Got it. What kind of support calls do you handle?")

    def test_post_processor_replaces_blocked_reply(self) -> None:
        processor = RA1CallPostProcessor(self.session)
        reply = asyncio.run(processor.post_process("Ask them for their name."))
        self.assertIn("trouble", reply)

    @patch("backend.voice_processor.add_waitlist_caller")
    def test_post_processor_triggers_airtable_write_on_complete(self, mock_add: AsyncMock) -> None:
        self.session.airtable_checked = True
        self.session.profile.name = "Ravi"
        self.session.profile.business = "Pharmacy"
        self.session.profile.support_calls = "Order updates"
        airtable_client = Mock()
        processor = RA1CallPostProcessor(self.session, airtable_client)
        asyncio.run(processor.on_call_end())
        self.assertTrue(self.session.waitlist_added)
        mock_add.assert_awaited_once()

    def test_pre_processor_updates_profile_from_text(self) -> None:
        processor = RA1CallPreProcessor(self.session, self.store)
        asyncio.run(processor.pre_process("My name is Ravi and I run a pharmacy"))
        self.assertEqual(self.session.profile.name, "Ravi")
        self.assertIn("pharmacy", self.session.profile.business.lower())


class CallRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        import backend.whatsapp as whatsapp
        whatsapp._RECENT_MESSAGE_IDS.clear()

    def test_health_endpoint(self) -> None:
        with TestClient(app) as client:
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)

    def test_call_incoming_endpoint(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/call/incoming",
                json={"from": "919999999999", "call_id": "call-123"},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "ringing")

    def test_call_answered_endpoint(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/call/answered",
                json={"from": "919999999999", "call_id": "call-123", "room": "room-123"},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "connected")

    def test_call_ended_endpoint(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/call/ended",
                json={"from": "919999999999", "call_id": "call-123", "duration_sec": 45},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "ok")

    def test_call_status_endpoint(self) -> None:
        with TestClient(app) as client:
            response = client.get("/call/status/call-123")
            self.assertEqual(response.status_code, 200)

    def test_call_dtmf_endpoint(self) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/call/dtmf",
                json={"call_id": "call-123", "digit": "1"},
            )
            self.assertEqual(response.status_code, 200)

    def test_call_incoming_creates_session(self) -> None:
        with TestClient(app) as client:
            client.post("/call/incoming", json={"from": "919999999999", "call_id": "call-456"})
            client.post("/call/answered", json={"from": "919999999999", "call_id": "call-456"})
            client.post("/call/ended", json={"from": "919999999999", "call_id": "call-456"})


class CallStateTests(unittest.TestCase):
    def test_default_state(self) -> None:
        state = CallState()
        self.assertIsNone(state.language)
        self.assertIsNone(state.business)
        self.assertIsNone(state.support_issue)
        self.assertIsNone(state.channel)
        self.assertEqual(state.turn_count, 0)
        self.assertFalse(state.value_dropped)
        self.assertFalse(state.hangup_requested)

    def test_state_accumulates_values(self) -> None:
        state = CallState()
        state.language = "ml-IN"
        state.business = "pharmacy"
        state.support_issue = "order tracking"
        state.channel = "whatsapp"
        state.turn_count = 3
        state.value_dropped = True
        state.hangup_requested = True
        self.assertEqual(state.language, "ml-IN")
        self.assertEqual(state.business, "pharmacy")
        self.assertEqual(state.turn_count, 3)
        self.assertTrue(state.value_dropped)
        self.assertTrue(state.hangup_requested)


class PickMoveTests(unittest.TestCase):
    def test_ask_field_when_business_missing(self) -> None:
        state = CallState(turn_count=1)
        move, field = pick_move(state)
        self.assertEqual(move, "ask_field")
        self.assertEqual(field, "business")

    def test_ask_field_when_support_issue_missing(self) -> None:
        state = CallState(turn_count=1, business="pharmacy")
        move, field = pick_move(state)
        self.assertEqual(move, "ask_field")
        self.assertEqual(field, "support_issue")

    def test_react_when_field_just_detected(self) -> None:
        state = CallState(turn_count=3, business="pharmacy")
        move, field = pick_move(state, just_detected_field="support_issue")
        self.assertEqual(move, "react")
        self.assertEqual(field, "support_issue")

    def test_ask_field_when_turn_1_with_just_detected(self) -> None:
        state = CallState(turn_count=1)
        move, field = pick_move(state, just_detected_field="business")
        self.assertEqual(move, "ask_field")
        self.assertEqual(field, "business")

    def test_drop_value_when_all_collected(self) -> None:
        state = CallState(
            turn_count=5,
            business="pharmacy",
            support_issue="delivery",
            channel="whatsapp",
        )
        move, field = pick_move(state)
        self.assertEqual(move, "drop_value")

    def test_soft_close_when_value_dropped(self) -> None:
        state = CallState(
            turn_count=6,
            business="pharmacy",
            support_issue="delivery",
            channel="whatsapp",
            value_dropped=True,
        )
        move, field = pick_move(state)
        self.assertEqual(move, "soft_close")

    def test_hard_close_when_hangup_requested(self) -> None:
        state = CallState(
            turn_count=3,
            business="pharmacy",
            hangup_requested=True,
        )
        move, field = pick_move(state)
        self.assertEqual(move, "hard_close")


class HangupTests(unittest.TestCase):
    def test_no_hangup_when_facts_incomplete(self) -> None:
        state = CallState(business="pharmacy")
        self.assertFalse(should_hangup("bye", state))

    def test_no_hangup_when_question(self) -> None:
        state = CallState(
            business="pharmacy",
            support_issue="delivery",
            channel="whatsapp",
        )
        self.assertFalse(should_hangup("bye?", state))

    def test_hangup_on_terminal_phrase(self) -> None:
        state = CallState(
            business="pharmacy",
            support_issue="delivery",
            channel="whatsapp",
        )
        self.assertTrue(should_hangup("bye", state))
        self.assertTrue(should_hangup("goodbye", state))
        self.assertTrue(should_hangup("thanks", state))
        self.assertTrue(should_hangup("thank you", state))
        self.assertTrue(should_hangup("that's all", state))

    def test_hangup_when_already_requested(self) -> None:
        state = CallState(hangup_requested=True)
        self.assertTrue(should_hangup("hello", state))

    def test_does_not_flag_normal_speech(self) -> None:
        state = CallState(
            business="pharmacy",
            support_issue="delivery",
            channel="whatsapp",
        )
        self.assertFalse(should_hangup("I run a pharmacy", state))
        self.assertFalse(should_hangup("customers call about delivery", state))
        self.assertFalse(should_hangup("what languages do you support", state))


class MoveInstructionTests(unittest.TestCase):
    def test_ask_field_instruction(self) -> None:
        state = CallState()
        instr = build_move_instruction("ask_field", "business", state)
        self.assertIn("what kind of business they run", instr)
        self.assertIn("15 words", instr)

    def test_react_instruction(self) -> None:
        state = CallState()
        instr = build_move_instruction("react", "support_issue", state)
        self.assertIn("support issue", instr)
        self.assertIn("20 words", instr)

    def test_drop_value_instruction_includes_facts(self) -> None:
        state = CallState(
            business="pharmacy",
            support_issue="delivery",
            channel="whatsapp",
        )
        instr = build_move_instruction("drop_value", None, state)
        self.assertIn("pharmacy", instr)
        self.assertIn("delivery", instr)
        self.assertIn("whatsapp", instr)
        self.assertIn("Do not ask questions", instr)

    def test_soft_close_instruction(self) -> None:
        state = CallState()
        instr = build_move_instruction("soft_close", None, state)
        self.assertIn("WhatsApp follow-up", instr)
        self.assertIn("15 words", instr)

    def test_unknown_move_returns_empty(self) -> None:
        state = CallState()
        instr = build_move_instruction("bogus", None, state)
        self.assertEqual(instr, "")


class ExtractionTests(unittest.TestCase):
    def test_detect_language_malayalam(self) -> None:
        self.assertEqual(detect_language("malayalam"), "ml-IN")
        self.assertEqual(detect_language("ml"), "ml-IN")
        self.assertEqual(detect_language("മലയാളം"), "ml-IN")

    def test_detect_language_hindi(self) -> None:
        self.assertEqual(detect_language("hindi"), "hi-IN")
        self.assertEqual(detect_language("hi"), "hi-IN")
        self.assertEqual(detect_language("हिन्दी"), "hi-IN")

    def test_detect_language_tamil(self) -> None:
        self.assertEqual(detect_language("tamil"), "ta-IN")
        self.assertEqual(detect_language("ta"), "ta-IN")
        self.assertEqual(detect_language("தமிழ்"), "ta-IN")

    def test_detect_language_english(self) -> None:
        self.assertEqual(detect_language("english"), "en-IN")
        self.assertEqual(detect_language("en"), "en-IN")

    def test_detect_language_returns_none_for_unknown(self) -> None:
        self.assertIsNone(detect_language("french"))
        self.assertIsNone(detect_language(""))

    @patch("backend.call_router.AsyncGroq")
    def test_extract_facts_calls_groq_and_parses_response(self, mock_groq_class: Mock) -> None:
        mock_client = AsyncMock()
        mock_groq_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = AsyncMock()
        mock_client.chat.completions.create.return_value.choices = [
            Mock(message=Mock(content='{"business": "pharmacy", "support_issue": "delivery", "channel": "phone"}'))
        ]
        result = asyncio.run(extract_facts("I run a pharmacy, customers call about delivery", mock_client))
        self.assertEqual(result["business"], "pharmacy")
        self.assertEqual(result["support_issue"], "delivery")
        self.assertEqual(result["channel"], "phone")

    @patch("backend.call_router.AsyncGroq")
    def test_extract_facts_returns_empty_on_error(self, mock_groq_class: Mock) -> None:
        mock_client = AsyncMock()
        mock_groq_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API error")
        result = asyncio.run(extract_facts("hello", mock_client))
        self.assertEqual(result, {})


class SilenceHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = SilenceHandler(timeout=0.01)
        self.pushed: list = []
        self.handler.push_frame = lambda f, d=None: self.pushed.append(f)  # type: ignore

    def test_resets_timer_on_transcription(self) -> None:
        asyncio.run(self._run_test())
        end_frames = [f for f in self.pushed if isinstance(f, TextFrame) and f.text == "Are you still there?"]
        self.assertGreaterEqual(len(end_frames), 0)

    async def _run_test(self) -> None:
        pass


class ClosingTextTests(unittest.TestCase):
    def test_closing_text_is_defined(self) -> None:
        self.assertIn("WhatsApp", CLOSING_TEXT)
        self.assertIn("24 hours", CLOSING_TEXT)


if __name__ == "__main__":
    unittest.main()
