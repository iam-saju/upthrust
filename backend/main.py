import os
import base64
import httpx
import logging
import uuid
from pathlib import Path
from urllib.parse import quote
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response

# Load .env file for local development
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Buoyancy Labs Voice Demo")

# CORS for frontend
allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGIN", "*").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID", "X-User-Text", "X-Agent-Text", "X-Detected-Lang"],
)
logger.info(f"CORS allowed origins: {allowed_origins}")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
if not SARVAM_API_KEY:
    raise ValueError("SARVAM_API_KEY environment variable is required")

SARVAM_BASE = "https://api.sarvam.ai"

# RA-1 System Prompt
SYSTEM_PROMPT = """You are Ra.One (pronounced "R-A-One" like the Shahrukh Khan movie), a warm, helpful, and respectful voice customer support agent from Buoyancy Labs.

Your personality:
- Speak naturally like a friendly Indian customer support executive
- Be polite, patient, and solution-oriented
- Use simple, clear language
- Show empathy when the customer is frustrated
- Keep answers concise but helpful (1-2 sentences max)
- If you don't know something, say so honestly and offer alternatives

Tone: Warm, professional, and approachable. Never robotic.

Always respond in the same language the user is speaking (Hindi, Hinglish, Tamil, English, etc.).

Current company: Buoyancy Labs - We build voice AI agents for Indian businesses.
"""

LANGUAGE_MAP = {
    "en-IN": "en-IN",
    "hi-IN": "hi-IN",
    "ml-IN": "ml-IN",
    "ta-IN": "ta-IN",
}

SPEAKER_MAP = {
    "en-IN": "shubh",
    "hi-IN": "shubh",
    "ml-IN": "shubh",
    "ta-IN": "shubh",
}

GREETINGS_MAP = {
    "en-IN": "Hello! I am Ra.One, your voice assistant from Buoyancy Labs. How can I help you today?",
    "hi-IN": "नमस्ते! मैं बॉयन्सी लैब्स से रा.वन हूँ। मैं आपकी कैसे मदद कर सकता हूँ?",
    "ml-IN": "നമസ്കാരം! ഞാൻ ബോയൻസി ലാബ്സിൽ നിന്നുള്ള രാ.വൺ ആണ്. ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കാം?",
    "ta-IN": "வணக்கம்! நான் பாயன்சி லேப்ஸிலிருந்து ரா.வன். நான் உங்களுக்கு எப்படி உதவலாம்?",
}

# Simple in-memory conversation memory (session_id → list of messages)
# For demo only — no persistence
sessions: dict[str, list[dict]] = {}
MAX_HISTORY = 5  # Keep last 5 exchanges


async def stt(audio_bytes: bytes, language_code: str = "unknown") -> tuple[str, str]:
    """Send audio to Sarvam STT, return (transcribed_text, detected_language_code)."""
    logger.info(f"STT request: {len(audio_bytes)} bytes, language_code={language_code}")
    
    import asyncio
    
    max_retries = 2
    for attempt in range(max_retries + 1):
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try webm first, fallback to wav if needed
            for filename, content_type in [("audio.webm", "audio/webm"), ("audio.wav", "audio/wav")]:
                files = {"file": (filename, audio_bytes, content_type)}
                data = {
                    "model": "saaras:v3",
                    "mode": "transcribe",
                    "language_code": language_code,
                }
                headers = {"api-subscription-key": SARVAM_API_KEY}
                
                try:
                    resp = await client.post(
                        f"{SARVAM_BASE}/speech-to-text",
                        files=files,
                        data=data,
                        headers=headers,
                    )
                    
                    if resp.status_code == 200:
                        result = resp.json()
                        transcript = result.get("transcript") or ""
                        detected_lang = result.get("language_code", language_code)
                        logger.info(f"STT success: {transcript[:100] if transcript else '(empty)'} (detected: {detected_lang})")
                        return transcript, detected_lang
                    elif resp.status_code == 429:
                        if attempt < max_retries:
                            wait_time = 2 ** attempt
                            logger.warning(f"STT rate limited (429), retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                            await asyncio.sleep(wait_time)
                            break  # break inner loop, retry outer loop
                        else:
                            raise HTTPException(status_code=429, detail="STT rate limit exceeded")
                    else:
                        logger.warning(f"STT failed with {resp.status_code}: {resp.text[:200]}")
                        if content_type == "audio/wav":
                            if resp.status_code == 429 and attempt < max_retries:
                                wait_time = 2 ** attempt
                                logger.warning(f"STT rate limited (429), retrying in {wait_time}s")
                                await asyncio.sleep(wait_time)
                                break
                            raise HTTPException(status_code=400, detail=f"STT error: {resp.text}")
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"STT exception: {e}")
                    if content_type == "audio/wav":
                        raise HTTPException(status_code=500, detail=f"STT failed: {str(e)}")
    
    raise HTTPException(status_code=400, detail="STT failed for all formats")


async def llm(user_text: str, language_code: str, session_id: str) -> str:
    """Send text to Sarvam-30B LLM with conversation memory, return response."""
    import json as json_lib
    
    # Get or create session history
    if session_id not in sessions:
        sessions[session_id] = []
    
    history = sessions[session_id]
    
    # Build messages with system prompt + history + current user message
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-(MAX_HISTORY * 2):])
    messages.append({"role": "user", "content": user_text})
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "model": "sarvam-30b",
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": 2000,
        }
        headers = {
            "Authorization": f"Bearer {SARVAM_API_KEY}",
            "Content-Type": "application/json",
        }
        
        # Non-streaming for reliability (streaming was returning empty)
        resp = await client.post(
            f"{SARVAM_BASE}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        result = resp.json()
        response_text = result.get("choices", [{}])[0].get("message", {}).get("content") or ""
        
        # If LLM returned empty, use a fallback
        if not response_text.strip():
            logger.warning("LLM returned empty response, using fallback")
            response_text = "I'm Ra.One from Buoyancy Labs. How can I help you today?"
        
        # Update conversation memory (only if we have a real response)
        if response_text.strip():
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": response_text})
        
        return response_text


async def tts_stream(text: str, language_code: str):
    """Stream TTS audio from Sarvam HTTP Stream endpoint."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        payload = {
            "text": text,
            "model": "bulbul:v3",
            "target_language_code": language_code,
            "output_audio_codec": "mp3",
            "pace": 1.1,
        }
        logger.info(f"TTS request: language={language_code}, text={text[:50]}...")
        headers = {
            "api-subscription-key": SARVAM_API_KEY,
            "Content-Type": "application/json",
        }
        
        logger.info(f"TTS streaming: {text[:100]}...")
        
        async with client.stream(
            "POST",
            f"{SARVAM_BASE}/text-to-speech/stream",
            json=payload,
            headers=headers,
        ) as resp:
            if resp.status_code != 200:
                error_text = await resp.aread()
                logger.error(f"TTS stream error: {resp.status_code} - {error_text[:200]}")
                # Return silence instead of crashing
                yield b""
                return
            
            chunk_count = 0
            async for chunk in resp.aiter_bytes():
                chunk_count += 1
                yield chunk
            
            logger.info(f"TTS stream complete: {chunk_count} chunks")


@app.post("/talk")
async def talk(
    audio: UploadFile = File(...),
    session_id: str = Form(""),
    language: str = Form("en-IN"),
):
    """Main demo endpoint: audio in → AI voice out (streaming)."""
    logger.info(f"Talk request: session={session_id}, language={language}, content_type={audio.content_type}")
    
    if not audio.content_type or not audio.content_type.startswith("audio"):
        raise HTTPException(status_code=400, detail="Audio file required")
    
    # Generate session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())

    # Use frontend's selected language for TTS (fall back to en-IN if not supported)
    language_code = language if language in SPEAKER_MAP else "en-IN"

    try:
        # 1. STT — speech to text (uses selected language)
        audio_bytes = await audio.read()
        logger.info(f"Audio size: {len(audio_bytes)} bytes")
        user_text, detected_lang = await stt(audio_bytes, language_code)

        if not user_text or not user_text.strip():
            raise HTTPException(status_code=400, detail="No speech detected")

        # 2. LLM — generate response with conversation memory
        logger.info(f"User text: {user_text[:100]}")
        response_text = await llm(user_text, language_code, session_id)
        logger.info(f"LLM response: {response_text[:100] if response_text else '(empty)'}")
        
        # Fallback if LLM returns empty or None
        if not response_text or not response_text.strip():
            response_text = "I'm sorry, I didn't understand that. Could you please try again?"
            logger.warning("LLM returned empty, using fallback response")

        # 3. TTS — stream audio back
        logger.info("Starting TTS stream...")
        return StreamingResponse(
            tts_stream(response_text, language_code),
            media_type="audio/mpeg",
            headers={
                "X-Session-ID": session_id,
                "X-User-Text": quote(user_text),
                "X-Agent-Text": quote(response_text),
                "X-Detected-Lang": detected_lang,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Talk endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok", "service": "buoyancy-voice-demo"}


@app.post("/greet")
async def greet(language: str = Form("en-IN")):
    """Return immediate greeting audio for first turn."""
    language_code = language if language in SPEAKER_MAP else "en-IN"
    greeting = GREETINGS_MAP.get(language_code, GREETINGS_MAP["en-IN"])
    return StreamingResponse(
        tts_stream(greeting, language_code),
        media_type="audio/mpeg",
    )


@app.post("/clear-session")
async def clear_session(session_id: str = Form("")):
    """Clear conversation memory for a session."""
    if session_id and session_id in sessions:
        del sessions[session_id]
        return {"status": "cleared", "session_id": session_id}
    return {"status": "no session found"}
