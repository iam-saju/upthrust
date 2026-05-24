from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.llm_brain import extract_text_reply
from backend.llm_utils import normalize_language
from backend.ra1 import (
    BehaviorPlan,
    BUOYANCY_CORE_FACTS,
    RA1_SYSTEM_PROMPT,
    RenderRequest,
    SessionStore,
    build_ra1_messages,
    build_render_request,
    cap_reply_sentences,
    decide_turn,
    is_buoyancy_question,
    local_ra1_fallback,
    validate_user_facing_reply,
)
from backend.whatsapp import (
    StageTimer,
    WhatsAppDeps,
    add_waitlist_caller,
    detect_text_language,
    extract_whatsapp_messages,
    find_waitlist_caller,
    handle_whatsapp_message,
    message_audio_id,
    message_text_body,
    returning_caller_facts,
    stt_fallback_message,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class WhatsAppBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["WHATSAPP_VERIFY_TOKEN"] = "test-verify-token"
        os.environ["AIRTABLE_API_KEY"] = "airtable-key"
        os.environ["AIRTABLE_BASE_ID"] = "base-id"
        os.environ["AIRTABLE_WAITLIST_TABLE_NAME"] = "waitinlist"

    def load_fixture(self, name: str) -> dict:
        return json.loads((FIXTURES_DIR / name).read_text())

    def make_deps(self) -> tuple[WhatsAppDeps, SessionStore]:
        store = SessionStore()
        deps = WhatsAppDeps(
            logger=Mock(),
            meta_client_getter=lambda: object(),
            sarvam_client_getter=lambda: object(),
            airtable_client_getter=lambda: object(),
            session_store_getter=lambda: store,
        )
        return deps, store

    def test_health_endpoint(self) -> None:
        with TestClient(app) as client:
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok"})

    def test_webhook_verification_success(self) -> None:
        with TestClient(app) as client:
            response = client.get(
                "/whatsapp/webhook",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "test-verify-token",
                    "hub.challenge": "12345",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.text, "12345")

    def test_webhook_verification_failure(self) -> None:
        with TestClient(app) as client:
            response = client.get(
                "/whatsapp/webhook",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "wrong-token",
                    "hub.challenge": "12345",
                },
            )
            self.assertEqual(response.status_code, 403)

    def test_webhook_message_handling_uses_lifespan_clients(self) -> None:
        payload = self.load_fixture("whatsapp_text_message.json")
        with patch("backend.whatsapp.handle_whatsapp_message", new=AsyncMock()) as mocked_handler:
            with TestClient(app) as client:
                response = client.post("/whatsapp/webhook", json=payload)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"status": "ok"})
                mocked_handler.assert_awaited_once()

    def test_shared_clients_are_created_once_per_app_lifecycle(self) -> None:
        meta_client = AsyncMock()
        sarvam_client = AsyncMock()
        airtable_client = AsyncMock()
        with patch("backend.main.create_meta_client", return_value=meta_client) as create_meta:
            with patch("backend.main.create_sarvam_client", return_value=sarvam_client) as create_sarvam:
                with patch("backend.main.create_airtable_client", return_value=airtable_client) as create_airtable:
                    with TestClient(app) as client:
                        health_response = client.get("/health")
                        verify_response = client.get(
                            "/whatsapp/webhook",
                            params={
                                "hub.mode": "subscribe",
                                "hub.verify_token": "test-verify-token",
                                "hub.challenge": "12345",
                            },
                        )
                        self.assertEqual(health_response.status_code, 200)
                        self.assertEqual(verify_response.status_code, 200)

                    create_meta.assert_called_once()
                    create_sarvam.assert_called_once()
                    create_airtable.assert_called_once()
                    meta_client.aclose.assert_awaited_once()
                    sarvam_client.aclose.assert_awaited_once()
                    airtable_client.aclose.assert_awaited_once()

    def test_extract_text_message(self) -> None:
        payload = self.load_fixture("whatsapp_text_message.json")
        messages = extract_whatsapp_messages(payload)
        self.assertEqual(len(messages), 1)
        self.assertEqual(message_text_body(messages[0]), "hello")

    def test_extract_audio_message(self) -> None:
        payload = self.load_fixture("whatsapp_audio_message.json")
        messages = extract_whatsapp_messages(payload)
        self.assertEqual(len(messages), 1)
        self.assertEqual(message_audio_id(messages[0]), "media-audio-1")

    def test_normalize_language(self) -> None:
        self.assertEqual(normalize_language("hi"), "hi-IN")
        self.assertEqual(normalize_language("en-in"), "en-IN")

    def test_detect_text_language_from_script(self) -> None:
        self.assertEqual(detect_text_language("नमस्ते"), "hi-IN")
        self.assertEqual(detect_text_language("നമസ്കാരം"), "ml-IN")
        self.assertEqual(detect_text_language("வணக்கம்"), "ta-IN")
        self.assertEqual(detect_text_language("hello"), "en-IN")

    def test_llm_brain_is_adapter_only(self) -> None:
        payload = {"choices": [{"message": {"content": "Hello"}}]}
        self.assertEqual(extract_text_reply(payload), "Hello")

    def test_stage_timer_summary(self) -> None:
        timer = StageTimer()
        timer.start("llm")
        timer.end("llm")
        summary = timer.summary("text", "llm", "en-IN")
        self.assertEqual(summary["kind"], "text")
        self.assertEqual(summary["source"], "llm")
        self.assertEqual(summary["language"], "en-IN")
        self.assertIn("llm_ms", summary)
        self.assertIn("total_ms", summary)

    def test_build_render_request(self) -> None:
        _, store = self.make_deps()
        session = store.get("919999999999", "en-IN")
        session.profile.name = "Ravi"
        request = build_render_request(
            session,
            BehaviorPlan(intent="ask_business", ack="got_it", needs_followup=True),
        )
        self.assertEqual(request.intent, "ask_business")
        self.assertEqual(request.caller_name, "Ravi")
        self.assertTrue(request.needs_followup)

    def test_ra1_system_prompt_uses_memo_context_without_tool_claims(self) -> None:
        self.assertIn("inbound support operator for Buoyancy Labs", RA1_SYSTEM_PROMPT)
        self.assertIn("Indian businesses", RA1_SYSTEM_PROMPT)
        self.assertIn("WhatsApp and voice-first", RA1_SYSTEM_PROMPT)
        self.assertIn("Indian language mixing", RA1_SYSTEM_PROMPT)
        self.assertIn("Airtable lookup and waitlist writes are handled by the application", RA1_SYSTEM_PROMPT)
        self.assertNotIn("check_airtable(", RA1_SYSTEM_PROMPT)
        self.assertNotIn("add_to_waitlist(", RA1_SYSTEM_PROMPT)

    def test_render_payload_uses_less_instruction_leaky_final_line(self) -> None:
        messages = build_ra1_messages(
            [],
            RenderRequest(intent="ask_business", language_code="en-IN", stage="collect_business"),
        )
        payload = messages[-1]["content"]
        self.assertIn("Final reply only.", payload)
        self.assertNotIn("Return only the final customer-facing message.", payload)

    def test_render_payload_always_includes_buoyancy_core_facts(self) -> None:
        messages = build_ra1_messages(
            [],
            RenderRequest(intent="ask_business", language_code="en-IN", stage="collect_business"),
        )
        payload = messages[-1]["content"]
        self.assertIn("Buoyancy Labs facts:", payload)
        for fact in BUOYANCY_CORE_FACTS:
            self.assertIn(fact, payload)

    def test_local_ra1_fallback_is_customer_facing(self) -> None:
        fallback = local_ra1_fallback(
            RenderRequest(intent="ask_name", language_code="en-IN", stage="collect_name", ack="sorry")
        )
        self.assertTrue(fallback.startswith("Sorry"))
        self.assertNotIn("Say ", fallback)

    def test_validator_blocks_planner_language(self) -> None:
        self.assertFalse(validate_user_facing_reply("Say you did not catch their name."))
        self.assertFalse(validate_user_facing_reply("Ask what their business does."))
        self.assertFalse(validate_user_facing_reply("Greet warmly as RA-1 and ask for name."))
        self.assertFalse(validate_user_facing_reply("Please convert this customer-facing instruction."))
        self.assertTrue(validate_user_facing_reply("Got it. What kind of business are you running?"))

    def test_reply_cap_preserves_followup_sentence(self) -> None:
        capped = cap_reply_sentences(
            "Got it. We support Hindi and English. Someone will follow up within 24 hours on WhatsApp."
        )
        self.assertEqual(capped, "Got it. Someone will follow up within 24 hours on WhatsApp.")

    def test_faq_facts_do_not_use_planner_language(self) -> None:
        from backend.ra1 import FAQ_FACTS

        blocked = ("say ", "ask ", "mention ", "greet ")
        for fact_list in FAQ_FACTS.values():
            for fact in fact_list:
                self.assertFalse(fact.lower().startswith(blocked))

    def test_buoyancy_question_routes_to_answer_question(self) -> None:
        self.assertTrue(is_buoyancy_question("Buoyancy kya karta hai?"))
        session = SessionStore().get("919999999999", "en-IN")
        plan = decide_turn(session, "Tell me about your company")
        self.assertEqual(plan.intent, "answer_question")
        self.assertTrue(plan.needs_followup)
        self.assertIn(BUOYANCY_CORE_FACTS[0], plan.facts)

    def test_buoyancy_question_does_not_interrupt_collection_stage(self) -> None:
        session = SessionStore().get("919999999999", "en-IN")
        session.stage = "collect_business"
        plan = decide_turn(session, "We run a company doing logistics")
        self.assertEqual(plan.intent, "ask_support_calls")

    def test_find_waitlist_caller_phone_hit(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(return_value=FakeResponse({"records": [{"fields": {"name": "Ravi"}}]}))
        result = self._run_async(find_waitlist_caller(client=client, phone="919999999999"))
        self.assertEqual(result, {"name": "Ravi"})

    def test_find_waitlist_caller_name_fallback_hit(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(
            side_effect=[
                FakeResponse({"records": []}),
                FakeResponse({"records": [{"fields": {"name": "Asha"}}]}),
            ]
        )
        result = self._run_async(find_waitlist_caller(client=client, phone="919999999999", name="Asha"))
        self.assertEqual(result, {"name": "Asha"})

    def test_find_waitlist_caller_no_match(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(side_effect=[FakeResponse({"records": []}), FakeResponse({"records": []})])
        result = self._run_async(find_waitlist_caller(client=client, phone="919999999999", name="Asha"))
        self.assertIsNone(result)

    def test_add_waitlist_caller_success(self) -> None:
        _, store = self.make_deps()
        session = store.get("919999999999", "en-IN")
        session.profile.name = "Ravi"
        session.profile.business = "Runs a pharmacy"
        session.profile.support_calls = "Order updates and availability"
        session.profile.question = "How fast is setup?"
        client = AsyncMock()
        client.post = AsyncMock(return_value=FakeResponse({"id": "rec1"}))
        result = self._run_async(add_waitlist_caller(client=client, session=session))
        self.assertEqual(result, {"id": "rec1"})
        payload = client.post.await_args.kwargs["json"]["fields"]
        self.assertEqual(payload["name"], "Ravi")
        self.assertIn("Support calls:", payload["aim of your project"])

    def test_returning_caller_facts_include_record_context(self) -> None:
        facts = returning_caller_facts({"name": "Ravi", "aim of your project": "Pharmacy"})
        self.assertIn("Caller is a returning contact named Ravi.", facts)
        self.assertIn("Their business: Pharmacy.", facts)
        self.assertIn("Their setup is being reviewed by the Buoyancy team.", facts)

    def test_stt_fallback_message_uses_language(self) -> None:
        self.assertIn("Dobara", stt_fallback_message("hi-IN"))
        self.assertIn("Voice note", stt_fallback_message("ml-IN"))
        self.assertIn("Meendum", stt_fallback_message("ta-IN"))
        self.assertIn("I couldn't catch", stt_fallback_message("en-IN"))

    def test_new_caller_progression_adds_to_waitlist_and_closes(self) -> None:
        deps, store = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        with patch("backend.whatsapp.find_waitlist_caller", new=AsyncMock(return_value=None)):
            with patch("backend.whatsapp.add_waitlist_caller", new=AsyncMock(return_value={"id": "rec1"})) as added:
                with patch("backend.whatsapp.sarvam_chat_completion", new=AsyncMock(side_effect=[
                    "Got it. What kind of business are you running?",
                    "What kind of customer support calls do you get most?",
                    "Any specific questions about how this works?",
                    "Perfect. Someone from Buoyancy Labs will follow up within 24 hours on WhatsApp.",
                ])):
                    with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()):
                        self._run_async(handle_whatsapp_message(deps=deps, message=message))
                        message["text"] = {"body": "My name is Ravi"}
                        self._run_async(handle_whatsapp_message(deps=deps, message=message))
                        message["text"] = {"body": "We run a pharmacy"}
                        self._run_async(handle_whatsapp_message(deps=deps, message=message))
                        message["text"] = {"body": "Mostly order updates and medicine availability"}
                        self._run_async(handle_whatsapp_message(deps=deps, message=message))
                        message["text"] = {"body": "How fast is setup?"}
                        self._run_async(handle_whatsapp_message(deps=deps, message=message))

        added.assert_awaited_once()
        self.assertIsNone(store._sessions.get("919999999999"))

    def test_text_message_updates_language_from_script(self) -> None:
        deps, store = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        message["text"] = {"body": "नमस्ते"}
        with patch("backend.whatsapp.find_waitlist_caller", new=AsyncMock(return_value=None)):
            with patch("backend.whatsapp.sarvam_chat_completion", new=AsyncMock()):
                with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()):
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))

        self.assertEqual(store.get("919999999999").language_code, "hi-IN")
        summary = self._extract_latency_summary(deps.logger.info.call_args_list)
        self.assertEqual(summary["language"], "hi-IN")

    def test_returning_caller_flow_gives_status_update(self) -> None:
        deps, store = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        with patch("backend.whatsapp.find_waitlist_caller", new=AsyncMock(return_value={"name": "Ravi", "aim of your project": "Pharmacy"})):
            with patch("backend.whatsapp.sarvam_chat_completion", new=AsyncMock(side_effect=[
                "Welcome back Ravi. Your setup is being reviewed. What would you like help with today?",
                "We support Hindi, Tamil, Malayalam, Hinglish, and English. We will follow up within 24 hours on WhatsApp.",
            ])):
                with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()):
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))
                    message["text"] = {"body": "My name is Ravi"}
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))
                    message["text"] = {"body": "What languages do you support?"}
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))

        self.assertIsNone(store._sessions.get("919999999999"))

    def test_unclear_name_triggers_clarification(self) -> None:
        deps, _ = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        with patch("backend.whatsapp.sarvam_chat_completion", new=AsyncMock(side_effect=[
            "Sorry, I missed your name. What should I call you?",
        ])):
            with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()):
                self._run_async(handle_whatsapp_message(deps=deps, message=message))
                message["text"] = {"body": "Yes"}
                self._run_async(handle_whatsapp_message(deps=deps, message=message))

        summary = self._extract_latency_summary(deps.logger.info.call_args_list)
        self.assertEqual(summary["kind"], "text")

    def test_audio_caller_path_preserves_ra1_logic(self) -> None:
        deps, _ = self.make_deps()
        message = self.load_fixture("whatsapp_audio_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]

        with patch("backend.whatsapp.fetch_whatsapp_media_metadata", new=AsyncMock(return_value={"url": "https://example.com/audio", "mime_type": "audio/ogg"})):
            with patch("backend.whatsapp.download_whatsapp_media", new=AsyncMock(return_value=b"audio-bytes")):
                with patch("backend.whatsapp.sarvam_transcribe_audio", new=AsyncMock(return_value=("hello", "en-IN"))):
                    with patch("backend.whatsapp.sarvam_chat_completion", new=AsyncMock()) as chat:
                        with patch("backend.whatsapp.sarvam_synthesize_speech", new=AsyncMock(return_value=b"mp3-bytes")):
                            with patch("backend.whatsapp.upload_whatsapp_media", new=AsyncMock(return_value="media-id")):
                                with patch("backend.whatsapp.send_whatsapp_audio", new=AsyncMock()):
                                    self._run_async(handle_whatsapp_message(deps=deps, message=message))

        chat.assert_not_awaited()

        summary = self._extract_latency_summary(deps.logger.info.call_args_list)
        self.assertEqual(summary["kind"], "audio")
        self.assertIn("stt_ms", summary)
        self.assertIn("tts_ms", summary)

    def test_mandatory_close_promise_present_on_completed_flow(self) -> None:
        deps, _ = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        with patch("backend.whatsapp.find_waitlist_caller", new=AsyncMock(return_value={"name": "Ravi"})):
            with patch("backend.whatsapp.sarvam_chat_completion", new=AsyncMock(side_effect=[
                "Welcome back Ravi. Your setup is being reviewed. What would you like help with today?",
                "We will follow up within 24 hours on WhatsApp.",
            ])):
                with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))
                    message["text"] = {"body": "My name is Ravi"}
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))
                    message["text"] = {"body": "No"}
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))

        final_body = sender.await_args.kwargs["body"]
        self.assertIn("24 hours", final_body)

    def test_identity_question_is_deterministic(self) -> None:
        deps, _ = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        message["text"] = {"body": "Who are you?"}
        with patch("backend.whatsapp.sarvam_chat_completion", new=AsyncMock(return_value="I’m RA-1, customer support agent from Buoyancy Labs.")):
            with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                self._run_async(handle_whatsapp_message(deps=deps, message=message))
        self.assertIn("customer support agent", sender.await_args.kwargs["body"])

    def test_first_message_uses_hardcoded_greeting_without_llm(self) -> None:
        deps, store = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        with patch("backend.whatsapp.find_waitlist_caller", new=AsyncMock(return_value=None)):
            with patch("backend.whatsapp.sarvam_chat_completion", new=AsyncMock()) as chat:
                with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))

        chat.assert_not_awaited()
        self.assertEqual(
            sender.await_args.kwargs["body"],
            "Namaste! I'm RA-1 from Buoyancy Labs. What's your name and what does your business do?",
        )
        history = store.get("919999999999").history
        self.assertEqual(history[-1]["role"], "assistant")
        self.assertNotIn("Greet warmly", history[-1]["content"])

    def test_unsafe_model_output_falls_back_safely(self) -> None:
        deps, _ = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        with patch("backend.whatsapp.find_waitlist_caller", new=AsyncMock(return_value=None)):
            with patch("backend.whatsapp.sarvam_chat_completion", new=AsyncMock(return_value="Greet warmly as RA-1 and ask for name.")):
                with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))
                    message["text"] = {"body": "My name is Ravi"}
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))

        body = sender.await_args.kwargs["body"]
        self.assertNotIn("Greet warmly", body)
        self.assertIn("business", body)

    def test_llm_failure_during_business_stage_uses_stage_fallback(self) -> None:
        deps, _ = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        with patch("backend.whatsapp.find_waitlist_caller", new=AsyncMock(return_value=None)):
            with patch("backend.whatsapp.sarvam_chat_completion", new=AsyncMock(side_effect=RuntimeError("empty reply"))):
                with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))
                    message["text"] = {"body": "My name is Ravi"}
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))

        self.assertEqual(sender.await_args.kwargs["body"], "Got it. What kind of business are you running?")

    def test_session_history_stores_only_user_visible_messages(self) -> None:
        deps, store = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        with patch("backend.whatsapp.find_waitlist_caller", new=AsyncMock(return_value=None)):
            with patch("backend.whatsapp.sarvam_chat_completion", new=AsyncMock(return_value="Got it. What kind of business are you running?")):
                with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()):
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))
                    message["text"] = {"body": "My name is Ravi"}
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))

        history_text = "\n".join(item["content"] for item in store.get("919999999999").history)
        self.assertNotIn("Intent:", history_text)
        self.assertNotIn("Return only", history_text)

    def test_airtable_prefetch_failure_does_not_block_greeting(self) -> None:
        deps, _ = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        with patch("backend.whatsapp.find_waitlist_caller", new=AsyncMock(side_effect=RuntimeError("airtable down"))):
            with patch("backend.whatsapp.sarvam_chat_completion", new=AsyncMock()) as chat:
                with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                    self._run_async(handle_whatsapp_message(deps=deps, message=message))

        chat.assert_not_awaited()
        self.assertIn("RA-1 from Buoyancy Labs", sender.await_args.kwargs["body"])
        deps.logger.warning.assert_called()

    def _extract_latency_summary(self, call_args_list):
        summaries = []
        for call in call_args_list:
            if call.args and call.args[0] == "WA_LATENCY %s":
                summaries.append(call.args[1])
        if not summaries:
            self.fail("WA_LATENCY summary log not found")
        return summaries[-1]

    def _run_async(self, coroutine):
        import asyncio

        return asyncio.run(coroutine)


if __name__ == "__main__":
    unittest.main()
