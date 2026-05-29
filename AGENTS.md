<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

<!-- BEGIN:voice-call-agent-progress -->
# Voice Call Agent Progress

## Status (28 May 2026)
- **97 tests pass** (61 WhatsApp + 36 voice calls)
- All voice call endpoints tested: `/call/incoming`, `/call/answered`, `/call/ended`, `/call/status/{call_id}`, `/call/dtmf`
- Session lifecycle tested: creation, retrieval, clearing, profile extraction

## Files Created
- `backend/voice_session.py` — `CallSessionStore`, `CallSession`, `CallProfile`, profile extraction, greeting/farewell detection
- `backend/voice_agent.py` — RA-1 call prompt, message builder, validation/sanitization, localized responses
- `backend/voice_processor.py` — `RA1CallPreProcessor` (greeting/farewell fast-path, Airtable prefetch) and `RA1CallPostProcessor` (reply validation, Airtable write on profile complete)
- `backend/call_router.py` — FastAPI router with call lifecycle endpoints, `CallDeps` with lazy getters
- `tests/test_voice_calls.py` — 36 tests across sessions, agent, processors, and router

## Changes to Existing Files
- `backend/main.py` — Added `CallSessionStore` to lifespan, mounted `call_router` with lazy getter pattern
- `backend/requirements.txt` — Added `pipecat-ai[sarvam]`, `livekit-agents`, `livekit-api`
- `.env` — Added `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_URL`, `WHATSAPP_CALL_CALLBACK_URL`, and voice model overrides

## Known Issues / Fixes Applied
1. `deps.session_store` is a getter method, not a property — must call `deps.session_store()` not `deps.session_store`
2. Airtable write test mocks `add_waitlist_caller` directly (via `@patch("backend.voice_processor.add_waitlist_caller")`) — the real function expects an `httpx.Response` with `.raise_for_status()`, not a bare dict

## Next Steps (Not Started)
1. Install pipecat and livekit packages in the venv
2. Wire LiveKit `VoicePipelineAgent` into `/call/answered` — create room participant, instantiate Pipecat pipeline with SarvamSTT + GroqLLM + SarvamTTS + custom frame processors
3. Set up LiveKit Cloud project and configure SIP trunk
4. Activate WhatsApp Calling API in Meta Business Account, point callback to `/call/incoming`
5. Test end-to-end: WhatsApp call → LiveKit SIP → Pipecat pipeline → audio reply
<!-- END:voice-call-agent-progress -->
