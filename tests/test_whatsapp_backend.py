from __future__ import annotations

import json
import os
import unittest
import asyncio
from pathlib import Path
from unittest.mock import ANY, AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.airtable import (
    add_waitlist_caller,
    create_waitlist_lead,
    find_waitlist_caller,
    find_waitlist_caller_by_name,
    format_waitlist_business,
    update_waitlist_lead,
    waitlist_business_from_record,
)
from backend.conversation import (
    DEMO_INTRO,
    DIRECT_LLM_FALLBACK,
    DIRECT_STT_FALLBACK,
    PRODUCT_INTRO,
    DirectCallerSession,
    DirectSessionStore,
    business_captured_reply,
    build_direct_llm_messages,
    extract_business_type,
    handle_direct_turn,
)
from backend.llm_brain import extract_text_reply
from backend import llm_brain
from backend.llm_providers.sarvam import chat_complete, default_chat_model
from backend.llm_utils import normalize_language
from backend.ra1 import (
    BUOYANCY_CORE_FACTS,
    RA1_SYSTEM_PROMPT,
    SessionStore,
    build_messages,
    cap_reply_sentences,
    extract_name,
    get_closing,
    get_fallback,
    get_greeting,
    get_stt_fallback,
    is_closing,
    is_farewell,
    is_greeting,
    is_ready_to_write,
    sanitize_user_facing_reply,
    update_profile_from_text,
    validate_user_facing_reply,
)
from backend.whatsapp import (
    AUDIO_REPLY_TIMEOUT,
    StageTimer,
    WhatsAppDeps,
    create_tracked_background_task,
    detect_text_language,
    extract_whatsapp_messages,
    get_background_recovery,
    get_fast_ack,
    handle_whatsapp_message,
    message_audio_id,
    message_text_body,
    send_hybrid_text_reply,
    should_process_message,
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
        os.environ["CONVERSATION_DETERMINISTIC_MODE"] = "true"
        import backend.whatsapp as whatsapp

        whatsapp._RECENT_MESSAGE_IDS.clear()

    def load_fixture(self, name: str) -> dict:
        return json.loads((FIXTURES_DIR / name).read_text())

    def make_deps(self) -> tuple[WhatsAppDeps, DirectSessionStore]:
        store = DirectSessionStore()
        airtable_client = AsyncMock()
        deps = WhatsAppDeps(
            logger=Mock(),
            meta_client_getter=lambda: object(),
            sarvam_client_getter=lambda: object(),
            groq_client_getter=lambda: object(),
            airtable_client_getter=lambda: airtable_client,
            direct_session_store_getter=lambda: store,
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

    def test_sarvam_provider_sends_current_auth_headers(self) -> None:
        client = AsyncMock()
        client.post = AsyncMock(return_value=FakeResponse({"choices": [{"message": {"content": "Hello"}}]}))
        result = self._run_async(
            chat_complete(
                client=client,
                messages=[{"role": "user", "content": "Hi"}],
                model="sarvam-30b",
                max_tokens=20,
            )
        )
        self.assertEqual(result, "Hello")
        headers = client.post.await_args.kwargs["headers"]
        payload = client.post.await_args.kwargs["json"]
        self.assertEqual(headers["Authorization"], "Bearer sk_2nsno8vh_C8kYUniS349fSiwv4h8PagLd")
        self.assertEqual(headers["api-subscription-key"], "sk_2nsno8vh_C8kYUniS349fSiwv4h8PagLd")
        self.assertNotIn("reasoning_effort", payload)

    def test_sarvam_provider_defaults_to_fast_non_reasoning_model(self) -> None:
        self.assertEqual(default_chat_model(), "sarvam-30b")

    def test_sarvam_provider_honors_chat_model_env(self) -> None:
        with patch.dict(os.environ, {"SARVAM_CHAT_MODEL": "sarvam-30b"}):
            self.assertEqual(default_chat_model(), "sarvam-30b")
        with patch.dict(os.environ, {"SARVAM_CHAT_MODEL": "custom-fast-model"}):
            self.assertEqual(default_chat_model(), "custom-fast-model")

    def test_sarvam_provider_strips_think_blocks(self) -> None:
        client = AsyncMock()
        client.post = AsyncMock(
            return_value=FakeResponse(
                {"choices": [{"message": {"content": "<think>hidden reasoning</think>\n\nFinal answer."}}]}
            )
        )
        result = self._run_async(
            chat_complete(
                client=client,
                messages=[{"role": "user", "content": "Hi"}],
                model="sarvam-m",
                max_tokens=20,
            )
        )
        self.assertEqual(result, "Final answer.")

    def test_llm_brain_uses_chat_max_tokens_env(self) -> None:
        client = AsyncMock()
        with patch.dict(os.environ, {"GROQ_CHAT_MAX_TOKENS": "77"}):
            with patch("backend.llm_brain._groq_complete", new=AsyncMock(return_value="Hello")) as complete:
                result = self._run_async(llm_brain.generate_reply(client, [{"role": "user", "content": "Hi"}]))
        self.assertEqual(result, "Hello")
        self.assertEqual(complete.await_args.kwargs["max_tokens"], 77)

    def test_llm_brain_retries_empty_thinking_reply_with_forced_final_prompt(self) -> None:
        client = AsyncMock()
        messages = [
            {"role": "system", "content": "You are a WhatsApp assistant."},
            {"role": "user", "content": "Can I send a voice note not about my business?"},
        ]
        with patch(
            "backend.llm_brain._groq_complete",
            new=AsyncMock(side_effect=[RuntimeError("Groq chat returned an empty reply payload={}"), "Yes, send it here and I'll guide you."]),
        ) as complete:
            result = self._run_async(llm_brain.generate_reply(client, messages))
        self.assertEqual(result, "Yes, send it here and I'll guide you.")
        self.assertEqual(complete.await_count, 2)
        retry_messages = complete.await_args.kwargs["messages"]
        self.assertEqual(sum(1 for message in retry_messages if message["role"] == "system"), 1)
        self.assertIn("Output only the final user-visible WhatsApp reply", retry_messages[0]["content"])

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

    def test_fast_ack_and_background_recovery_are_localized(self) -> None:
        self.assertEqual(get_fast_ack("hi-IN"), "Theek hai, abhi check kar raha hoon.")
        self.assertIn("24 ghante", get_background_recovery("hi-IN"))
        self.assertEqual(get_fast_ack("unknown"), "Got it, checking that now.")

    def test_ra1_system_prompt_matches_new_context_driven_design(self) -> None:
        self.assertIn("inbound support operator for Buoyancy Labs", RA1_SYSTEM_PROMPT)
        self.assertIn("recent visible conversation history", RA1_SYSTEM_PROMPT)
        self.assertIn("known_caller is true", RA1_SYSTEM_PROMPT)
        self.assertNotIn("BehaviorPlan", RA1_SYSTEM_PROMPT)

    def test_build_messages_includes_context_history_and_facts(self) -> None:
        store = SessionStore()
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
        messages = build_messages(session, "What do you do?")
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(sum(1 for message in messages if message["role"] == "system"), 1)
        context_payload = messages[0]["content"]
        self.assertIn("Caller language: en-IN", context_payload)
        self.assertIn("Known caller: True", context_payload)
        self.assertIn("Returning caller business: Pharmacy", context_payload)
        self.assertIn("Generate a natural voice reply only.", context_payload)
        for fact in BUOYANCY_CORE_FACTS:
            self.assertIn(fact, context_payload)
        self.assertEqual(messages[-1], {"role": "user", "content": "What do you do?"})

    def test_validator_blocks_planner_language(self) -> None:
        self.assertFalse(validate_user_facing_reply("Say you did not catch their name."))
        self.assertFalse(validate_user_facing_reply("Ask what their business does."))
        self.assertFalse(validate_user_facing_reply("Greet warmly as RA-1 and ask for name."))
        self.assertTrue(validate_user_facing_reply("Got it. What kind of business are you running?"))

    def test_reply_cap_preserves_followup_sentence(self) -> None:
        capped = cap_reply_sentences(
            "Got it. We support Hindi and English. Someone will follow up within 24 hours on WhatsApp."
        )
        self.assertEqual(capped, "Got it. Someone will follow up within 24 hours on WhatsApp.")

    def test_update_profile_from_text_extracts_name_and_email_without_overwrite(self) -> None:
        session = SessionStore().get("919999999999", "en-IN")
        update_profile_from_text(session, "My name is Ravi and my email is ravi@example.com")
        self.assertEqual(session.profile.name, "Ravi")
        self.assertEqual(session.profile.email, "ravi@example.com")
        update_profile_from_text(session, "My name is Asha")
        self.assertEqual(session.profile.name, "Ravi")

    def test_extract_name_handles_short_name_only_text(self) -> None:
        self.assertEqual(extract_name("ravi"), "Ravi")

    def test_sanitize_user_facing_reply_rejects_malformed_or_instructional_text(self) -> None:
        self.assertEqual(sanitize_user_facing_reply("```system```"), "")
        self.assertEqual(sanitize_user_facing_reply("- Ask for business"), "")
        self.assertEqual(sanitize_user_facing_reply("  Got it. What kind of business are you running?  "), "Got it. What kind of business are you running?")

    def test_update_profile_from_text_avoids_ambiguous_business_assignment(self) -> None:
        session = SessionStore().get("919999999999", "en-IN")
        session.profile.name = "Ravi"
        update_profile_from_text(session, "Tell me more about pricing")
        self.assertEqual(session.profile.business, "")
        update_profile_from_text(session, "We run a pharmacy")
        self.assertEqual(session.profile.business, "We run a pharmacy")
        update_profile_from_text(session, "Mostly order updates and availability")
        self.assertEqual(session.profile.support_calls, "Mostly order updates and availability")

    def test_ready_to_write_requires_new_caller_with_collected_business(self) -> None:
        session = SessionStore().get("919999999999", "en-IN")
        session.airtable_checked = True
        session.profile.name = "Ravi"
        session.profile.business = "Pharmacy"
        self.assertTrue(is_ready_to_write(session))
        session.known_caller = True
        self.assertFalse(is_ready_to_write(session))

    def test_is_closing_recognizes_follow_up_phrases(self) -> None:
        self.assertTrue(is_closing("Someone from our team will follow up within 24 hours on WhatsApp."))
        self.assertTrue(is_closing("Hamari team 24 ghante mein follow up karegi."))
        self.assertFalse(is_closing("Tell me more about pricing."))

    def test_fast_path_helpers_cover_greeting_farewell_and_fallbacks(self) -> None:
        self.assertTrue(is_greeting("hello"))
        self.assertTrue(is_farewell("thanks"))
        self.assertIn("RA-1", get_greeting("en-IN"))
        self.assertIn("24 hours", get_closing("en-IN"))
        self.assertIn("Dobara", get_stt_fallback("hi-IN"))
        self.assertIn("send that once more", get_fallback("en-IN"))

    def test_extract_name_handles_possessive_name_phrase(self) -> None:
        self.assertEqual(extract_name("My name's saju"), "Saju")

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
        client.get = AsyncMock(
            side_effect=[
                FakeResponse({"records": []}),
                FakeResponse({"records": []}),
                FakeResponse({"records": []}),
            ]
        )
        result = self._run_async(find_waitlist_caller(client=client, phone="919999999999", name="Asha"))
        self.assertIsNone(result)

    def test_find_waitlist_caller_by_name_hit(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(return_value=FakeResponse({"records": [{"fields": {"name": "Saju", "aim of your project": "Hostel"}}]}))
        result = self._run_async(find_waitlist_caller_by_name(client=client, name="Saju"))
        self.assertEqual(result, {"name": "Saju", "aim of your project": "Hostel"})

    def test_find_waitlist_caller_by_name_is_case_and_spacing_tolerant(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(
            return_value=FakeResponse({"records": [{"fields": {"name": "Vinu Thomas", "whats your use ": "Textile shop"}}]})
        )
        result = self._run_async(find_waitlist_caller_by_name(client=client, name="vinu   thomas"))
        self.assertEqual(result, {"name": "Vinu Thomas", "whats your use ": "Textile shop"})
        formula = client.get.await_args.kwargs["params"]["filterByFormula"]
        self.assertIn("TRIM(LOWER({name}))", formula)
        self.assertIn("'vinu thomas'", formula)

    def test_waitlist_business_from_record_reads_whats_your_use_field(self) -> None:
        record = {"name": "Vinu Thomas", "whats your use ": "Textile business"}
        self.assertEqual(waitlist_business_from_record(record), "Textile business")

    def test_waitlist_business_from_record_normalizes_punctuated_use_field(self) -> None:
        record = {"name": "Saju Saju", "What's your use?": "mnc"}
        self.assertEqual(waitlist_business_from_record(record), "mnc")

    def test_add_waitlist_caller_success(self) -> None:
        store = SessionStore()
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
        self.assertEqual(payload["whats your use"], format_waitlist_business(session.profile))

    def test_create_waitlist_lead_uses_narrow_business_fields(self) -> None:
        client = AsyncMock()
        client.post = AsyncMock(return_value=FakeResponse({"id": "rec-new", "fields": {"name": "New Person"}}))
        result = self._run_async(
            create_waitlist_lead(
                client=client,
                name="New Person",
                phone="919999999999",
                business_use="Runs a textile shop",
                question="Need WhatsApp support",
            )
        )
        self.assertEqual(result["id"], "rec-new")
        fields = client.post.await_args.kwargs["json"]["fields"]
        self.assertEqual(fields["name"], "New Person")
        self.assertEqual(fields["phone no"], 919999999999)
        self.assertEqual(fields["whats your use"], "Runs a textile shop")
        self.assertEqual(fields["Question"], "Need WhatsApp support")

    def test_update_waitlist_lead_patches_existing_record(self) -> None:
        client = AsyncMock()
        client.patch = AsyncMock(return_value=FakeResponse({"id": "rec-existing"}))
        result = self._run_async(
            update_waitlist_lead(
                client=client,
                record_id="rec-existing",
                name="Saju Saju",
                phone="916282355292",
                business_use="mnc",
            )
        )
        self.assertEqual(result["id"], "rec-existing")
        self.assertTrue(client.patch.await_args.args[0].endswith("/rec-existing"))
        self.assertEqual(client.patch.await_args.kwargs["json"]["fields"]["whats your use"], "mnc")

    def test_direct_llm_messages_use_one_system_prompt(self) -> None:
        messages = build_direct_llm_messages("Who are you?", "en-IN")
        self.assertEqual(sum(1 for message in messages if message["role"] == "system"), 1)
        self.assertIn("AI customer support agent powered by Buoyancy Labs", messages[0]["content"])
        self.assertIn("Pricing is discussed during follow-up only", messages[0]["content"])
        self.assertIn("Business type: not known yet", messages[0]["content"])
        self.assertEqual(messages[-1], {"role": "user", "content": "Who are you?"})

    def test_direct_llm_messages_can_use_known_business_compat_argument(self) -> None:
        messages = build_direct_llm_messages("What can you do for me?", "en-IN", known_name="Saju", known_business="Hostel")
        self.assertIn("Business type: Hostel", messages[0]["content"])
        self.assertIn("deployed WhatsApp AI support assistant", messages[0]["content"])

    def test_direct_llm_messages_include_session_business_and_history(self) -> None:
        session = DirectCallerSession(phone="919999999999")
        session.business_type = "small bakery shop"
        session.history = [
            {"role": "user", "content": "I run a small bakery shop"},
            {"role": "assistant", "content": business_captured_reply("small bakery shop")},
        ]
        messages = build_direct_llm_messages("A customer says their cake is late", "en-IN", session=session)
        self.assertIn("Business type: small bakery shop", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[2]["role"], "assistant")
        self.assertEqual(messages[-1], {"role": "user", "content": "A customer says their cake is late"})

    def test_greeting_asks_for_business_without_calling_llm(self) -> None:
        deps, _ = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        message["text"] = {"body": "Hi"}
        with patch("backend.conversation.generate_reply", new=AsyncMock()) as chat:
            with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                self._run_async(handle_whatsapp_message(deps=deps, message=message))
        chat.assert_not_awaited()
        self.assertEqual(sender.await_args.kwargs["body"], DEMO_INTRO)
        summary = self._extract_latency_summary(deps.logger.info.call_args_list)
        self.assertEqual(summary["source"], "demo_intro")

    def test_business_statement_stores_business_without_calling_llm(self) -> None:
        deps, store = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        session = store.get(message["from"])
        message["text"] = {"body": "I run a garage"}
        with patch("backend.conversation.generate_reply", new=AsyncMock()) as chat:
            with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                self._run_async(handle_whatsapp_message(deps=deps, message=message))
        chat.assert_not_awaited()
        self.assertEqual(session.business_type, "garage")
        self.assertIn("support for your garage", sender.await_args.kwargs["body"])
        self.assertIn("message me like a customer", sender.await_args.kwargs["body"])
        summary = self._extract_latency_summary(deps.logger.info.call_args_list)
        self.assertEqual(summary["source"], "business_captured")

    def test_product_question_before_business_explains_and_asks_business(self) -> None:
        deps, store = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        message["text"] = {"body": "What does Buoyancy Labs do?"}
        with patch("backend.conversation.generate_reply", new=AsyncMock()) as chat:
            with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                self._run_async(handle_whatsapp_message(deps=deps, message=message))
        chat.assert_not_awaited()
        self.assertEqual(store.get(message["from"]).business_type, "")
        self.assertEqual(sender.await_args.kwargs["body"], PRODUCT_INTRO)
        summary = self._extract_latency_summary(deps.logger.info.call_args_list)
        self.assertEqual(summary["source"], "product_intro")

    def test_customer_message_after_business_goes_to_llm_with_business_context(self) -> None:
        deps, store = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        session = store.get(message["from"])
        session.business_type = "garage"
        message["text"] = {"body": "My car service is delayed"}
        with patch("backend.conversation.generate_reply", new=AsyncMock(return_value="Sorry about the delay. Please share your vehicle number so I can check the service status.")) as chat:
            with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                self._run_async(handle_whatsapp_message(deps=deps, message=message))
        chat.assert_awaited_once()
        messages = chat.await_args.args[1]
        self.assertIn("Business type: garage", messages[0]["content"])
        self.assertIn("deployed WhatsApp AI support assistant", messages[0]["content"])
        self.assertEqual(sender.await_args.kwargs["body"], "Sorry about the delay. Please share your vehicle number so I can check the service status.")
        summary = self._extract_latency_summary(deps.logger.info.call_args_list)
        self.assertEqual(summary["source"], "direct_llm")

    def test_business_change_updates_context_without_template_tree(self) -> None:
        session = DirectCallerSession(phone="919999999999", business_type="garage")
        result = self._run_async(
            handle_direct_turn(
                logger=Mock(),
                llm_client=object(),
                airtable_client=object(),
                session=session,
                user_text="Actually I run a salon",
                language_code="en-IN",
            )
        )
        self.assertEqual(session.business_type, "salon")
        self.assertEqual(result.source, "business_updated")
        self.assertIn("support for your salon", result.reply)

    def test_extract_business_type_is_lightweight_free_text(self) -> None:
        self.assertEqual(extract_business_type("I run a car rental business."), "car rental")
        self.assertEqual(extract_business_type("garage"), "garage")
        self.assertEqual(extract_business_type("What does Buoyancy Labs do?"), "")

    def test_conversation_turns_do_not_call_airtable(self) -> None:
        session = DirectCallerSession(phone="919999999999")
        airtable_client = AsyncMock()
        result = self._run_async(
            handle_direct_turn(
                logger=Mock(),
                llm_client=object(),
                airtable_client=airtable_client,
                session=session,
                user_text="I run a garage",
                language_code="en-IN",
            )
        )
        self.assertEqual(result.source, "business_captured")
        airtable_client.get.assert_not_called()
        airtable_client.post.assert_not_called()
        airtable_client.patch.assert_not_called()

    def test_text_message_llm_failure_sends_direct_fallback(self) -> None:
        deps, store = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        store.get(message["from"]).business_type = "garage"
        message["text"] = {"body": "What can you do?"}
        with patch("backend.conversation.generate_reply", new=AsyncMock(side_effect=RuntimeError("chat down"))):
            with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                self._run_async(handle_whatsapp_message(deps=deps, message=message))
        self.assertEqual(sender.await_args.kwargs["body"], DIRECT_LLM_FALLBACK)
        summary = self._extract_latency_summary(deps.logger.info.call_args_list)
        self.assertEqual(summary["source"], "direct_fallback")

    def test_text_send_failure_does_not_raise_from_handler(self) -> None:
        deps, store = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        store.get(message["from"]).business_type = "garage"
        message["text"] = {"body": "What's Buoyancy Labs?"}
        with patch("backend.conversation.generate_reply", new=AsyncMock(return_value="Buoyancy Labs builds support agents.")):
            with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock(side_effect=RuntimeError("401 Unauthorized"))):
                self._run_async(handle_whatsapp_message(deps=deps, message=message))
        deps.logger.warning.assert_any_call("WhatsApp text send skipped/failed: %s: %s", "RuntimeError", ANY)

    def test_slow_text_turn_sends_ack_then_background_reply(self) -> None:
        deps, store = self.make_deps()
        session = store.get("919999999999")

        async def slow_turn(**kwargs):
            await asyncio.sleep(0.01)
            from backend.conversation import ConversationResult

            return ConversationResult(reply="Final answer.", source="direct_llm", airtable_status="found")

        async def run_case():
            timer = StageTimer()
            with patch.dict(os.environ, {"WHATSAPP_FAST_REPLY_TIMEOUT_MS": "1"}):
                with patch("backend.whatsapp.handle_direct_turn", side_effect=slow_turn):
                    with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                        await send_hybrid_text_reply(
                            deps=deps,
                            meta_client=object(),
                            llm_client=object(),
                            airtable_client=object(),
                            session=session,
                            from_number="919999999999",
                            user_text="What do you do?",
                            language_code="en-IN",
                            timer=timer,
                            turn_id="turn-test",
                            message_id="wamid.test.slow",
                        )
                        await asyncio.sleep(0.03)
                        return sender

        sender = self._run_async(run_case())
        bodies = [call.kwargs["body"] for call in sender.await_args_list]
        self.assertEqual(bodies, ["Got it, checking that now.", "Final answer."])
        summaries = self._latency_summaries(deps.logger.info.call_args_list)
        ack_summary = next(summary for summary in summaries if summary.get("hybrid") is True)
        self.assertEqual(ack_summary["turn_id"], "turn-test")
        self.assertEqual(ack_summary["message_id"], "wamid.test.slow")
        self.assertFalse(ack_summary["final_sent"])
        self.assertTrue(ack_summary["ack_sent"])
        self.assertTrue(
            any(
                call.args
                and call.args[0] == "WA_BACKGROUND source=%s language=%s background_ms=%s turn_id=%s message_id=%s final_sent=%s"
                and call.args[4] == "turn-test"
                and call.args[5] == "wamid.test.slow"
                and call.args[6] is True
                for call in deps.logger.info.call_args_list
            )
        )

    def test_slow_text_turn_background_failure_sends_recovery(self) -> None:
        deps, store = self.make_deps()
        session = store.get("919999999999")

        async def failing_turn(**kwargs):
            await asyncio.sleep(0.01)
            raise RuntimeError("background down")

        async def run_case():
            timer = StageTimer()
            with patch.dict(os.environ, {"WHATSAPP_FAST_REPLY_TIMEOUT_MS": "1"}):
                with patch("backend.whatsapp.handle_direct_turn", side_effect=failing_turn):
                    with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                        await send_hybrid_text_reply(
                            deps=deps,
                            meta_client=object(),
                            llm_client=object(),
                            airtable_client=object(),
                            session=session,
                            from_number="919999999999",
                            user_text="What do you do?",
                            language_code="hi-IN",
                            timer=timer,
                            turn_id="turn-fail",
                            message_id="wamid.test.fail",
                        )
                        await asyncio.sleep(0.03)
                        return sender

        sender = self._run_async(run_case())
        bodies = [call.kwargs["body"] for call in sender.await_args_list]
        self.assertEqual(bodies[0], "Theek hai, abhi check kar raha hoon.")
        self.assertIn("24 ghante", bodies[1])
        deps.logger.exception.assert_any_call(
            "Background reply failed turn_id=%s message_id=%s",
            "turn-fail",
            "wamid.test.fail",
        )
        self.assertTrue(
            any(
                call.args
                and call.args[0] == "WA_BACKGROUND_RECOVERY turn_id=%s message_id=%s recovery_sent=%s error=%s"
                and call.args[1] == "turn-fail"
                and call.args[2] == "wamid.test.fail"
                and call.args[3] is True
                for call in deps.logger.info.call_args_list
            )
        )

    def test_tracked_background_task_logs_unexpected_crash(self) -> None:
        deps, _ = self.make_deps()

        async def boom():
            raise RuntimeError("unexpected")

        async def run_case():
            task = create_tracked_background_task(
                deps,
                boom(),
                turn_id="turn-crash",
                message_id="wamid.crash",
            )
            await task

        self._run_async(run_case())
        deps.logger.exception.assert_any_call(
            "WA_BACKGROUND_CRASH turn_id=%s message_id=%s",
            "turn-crash",
            "wamid.crash",
        )

    def test_audio_flow_uses_stt_then_direct_llm_then_tts(self) -> None:
        deps, store = self.make_deps()
        message = self.load_fixture("whatsapp_audio_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        session = store.get(message["from"])
        session.business_type = "garage"
        with patch("backend.whatsapp.fetch_whatsapp_media_metadata", new=AsyncMock(return_value={"url": "https://example.com/audio", "mime_type": "audio/ogg"})):
            with patch("backend.whatsapp.download_whatsapp_media", new=AsyncMock(return_value=b"audio-bytes")):
                with patch("backend.whatsapp.sarvam_transcribe_audio", new=AsyncMock(return_value=("Can I use this after 6pm?", "en-IN"))):
                    with patch("backend.conversation.generate_reply", new=AsyncMock(return_value="Hello from LLM.")) as chat:
                        with patch("backend.whatsapp.sarvam_synthesize_speech", new=AsyncMock(return_value=b"mp3-bytes")):
                            with patch("backend.whatsapp.upload_whatsapp_media", new=AsyncMock(return_value="media-id")):
                                with patch("backend.whatsapp.send_whatsapp_audio", new=AsyncMock()) as audio_sender:
                                    self._run_async(handle_whatsapp_message(deps=deps, message=message))
        chat.assert_awaited_once()
        prompt = chat.await_args.args[1][0]["content"]
        self.assertIn("Business type: garage", prompt)
        audio_sender.assert_awaited_once()
        summary = self._extract_latency_summary(deps.logger.info.call_args_list)
        self.assertEqual(summary["kind"], "audio")
        self.assertEqual(summary["source"], "audio_direct_llm")
        self.assertIn("stt_ms", summary)
        self.assertIn("tts_ms", summary)

    def test_audio_tts_failure_sends_direct_llm_text_reply(self) -> None:
        deps, store = self.make_deps()
        message = self.load_fixture("whatsapp_audio_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        store.get(message["from"]).business_type = "garage"
        with patch("backend.whatsapp.fetch_whatsapp_media_metadata", new=AsyncMock(return_value={"url": "https://example.com/audio", "mime_type": "audio/ogg"})):
            with patch("backend.whatsapp.download_whatsapp_media", new=AsyncMock(return_value=b"audio-bytes")):
                with patch("backend.whatsapp.sarvam_transcribe_audio", new=AsyncMock(return_value=("What can you do?", "en-IN"))):
                    with patch("backend.conversation.generate_reply", new=AsyncMock(return_value="Hello from LLM.")):
                        with patch("backend.whatsapp.sarvam_synthesize_speech", new=AsyncMock(side_effect=RuntimeError("tts down"))):
                            with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                                self._run_async(handle_whatsapp_message(deps=deps, message=message))
        self.assertEqual(sender.await_args.kwargs["body"], "Hello from LLM.")
        summary = self._extract_latency_summary(deps.logger.info.call_args_list)
        self.assertEqual(summary["source"], "audio_direct_llm_tts_fallback")

    def test_audio_stt_failure_sends_direct_stt_fallback(self) -> None:
        deps, _ = self.make_deps()
        message = self.load_fixture("whatsapp_audio_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        with patch("backend.whatsapp.fetch_whatsapp_media_metadata", new=AsyncMock(return_value={"url": "https://example.com/audio", "mime_type": "audio/ogg"})):
            with patch("backend.whatsapp.download_whatsapp_media", new=AsyncMock(return_value=b"audio-bytes")):
                with patch("backend.whatsapp.sarvam_transcribe_audio", new=AsyncMock(side_effect=RuntimeError("stt down"))):
                    with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                        self._run_async(handle_whatsapp_message(deps=deps, message=message))
        self.assertEqual(sender.await_args.kwargs["body"], DIRECT_STT_FALLBACK)
        summary = self._extract_latency_summary(deps.logger.info.call_args_list)
        self.assertEqual(summary["source"], "audio_stt_fallback")

    def test_audio_conversation_timeout_sends_text_without_tts(self) -> None:
        deps, _ = self.make_deps()
        message = self.load_fixture("whatsapp_audio_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]

        async def slow_turn(**kwargs):
            await asyncio.sleep(0.02)

        with patch("backend.whatsapp.fetch_whatsapp_media_metadata", new=AsyncMock(return_value={"url": "https://example.com/audio", "mime_type": "audio/ogg"})):
            with patch("backend.whatsapp.download_whatsapp_media", new=AsyncMock(return_value=b"audio-bytes")):
                with patch("backend.whatsapp.sarvam_transcribe_audio", new=AsyncMock(return_value=("What can you do?", "en-IN"))):
                    with patch.dict(os.environ, {"WHATSAPP_AUDIO_CONVERSATION_TIMEOUT_MS": "1"}):
                        with patch("backend.whatsapp.handle_direct_turn", side_effect=slow_turn):
                            with patch("backend.whatsapp.sarvam_synthesize_speech", new=AsyncMock()) as tts:
                                with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()) as sender:
                                    self._run_async(handle_whatsapp_message(deps=deps, message=message))
        tts.assert_not_awaited()
        self.assertEqual(sender.await_args.kwargs["body"], AUDIO_REPLY_TIMEOUT)
        summary = self._extract_latency_summary(deps.logger.info.call_args_list)
        self.assertEqual(summary["source"], "audio_timeout_fallback")

    def test_duplicate_message_id_is_ignored(self) -> None:
        message = {"id": "wamid.same.1", "from": "919999999999", "text": {"body": "Hi"}}
        self.assertTrue(should_process_message(message))
        self.assertFalse(should_process_message(message))

    def test_text_message_updates_language_from_script_for_direct_llm(self) -> None:
        deps, _ = self.make_deps()
        message = self.load_fixture("whatsapp_text_message.json")["entry"][0]["changes"][0]["value"]["messages"][0]
        message["text"] = {"body": "नमस्ते"}
        with patch("backend.conversation.generate_reply", new=AsyncMock(return_value="नमस्ते!")):
            with patch("backend.whatsapp.send_whatsapp_text", new=AsyncMock()):
                self._run_async(handle_whatsapp_message(deps=deps, message=message))
        summary = self._extract_latency_summary(deps.logger.info.call_args_list)
        self.assertEqual(summary["language"], "hi-IN")

    def _extract_latency_summary(self, call_args_list):
        summaries = self._latency_summaries(call_args_list)
        if not summaries:
            self.fail("WA_LATENCY summary log not found")
        return summaries[-1]

    def _latency_summaries(self, call_args_list):
        summaries = []
        for call in call_args_list:
            if call.args and call.args[0] == "WA_LATENCY %s":
                summaries.append(call.args[1])
        return summaries

    def _run_async(self, coroutine):
        import asyncio

        return asyncio.run(coroutine)


if __name__ == "__main__":
    unittest.main()
