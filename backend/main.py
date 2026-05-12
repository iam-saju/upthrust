import os
import base64
import httpx
import logging
import uuid
from pathlib import Path
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

# CORS for Netlify frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGIN", "*")],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    "en": "en-IN",
    "hi": "hi-IN",
    "ml": "ml-IN",
}

SPEAKER_MAP = {
    "en-IN": "shubh",
    "hi-IN": "shubh",
    "ml-IN": "shubh",
}

# Simple in-memory conversation memory (session_id → list of messages)
# For demo only — no persistence
sessions: dict[str, list[dict]] = {}
MAX_HISTORY = 5  # Keep last 5 exchanges


async def stt(audio_bytes: bytes, language_code: str) -> str:
    """Send audio to Sarvam STT, return transcribed text."""
    logger.info(f"STT request: {len(audio_bytes)} bytes, language={language_code}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # For English, try without language_code first (auto-detect)
        # For Indic languages, always specify language_code
        language_param = language_code if language_code != "en-IN" else "unknown"
        
        # Try webm first, fallback to wav if needed
        for filename, content_type in [("audio.webm", "audio/webm"), ("audio.wav", "audio/wav")]:
            files = {"file": (filename, audio_bytes, content_type)}
            data = {
                "model": "saaras:v3",
                "mode": "transcribe",
                "language_code": language_param,
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
                    transcript = result.get("transcript", "")
                    detected_lang = result.get("language_code", "unknown")
                    logger.info(f"STT success: {transcript[:100]} (detected: {detected_lang})")
                    return transcript
                else:
                    logger.warning(f"STT failed with {resp.status_code}: {resp.text[:200]}")
                    if content_type == "audio/wav":
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
    # Get or create session history
    if session_id not in sessions:
        sessions[session_id] = []
    
    history = sessions[session_id]
    
    # Build messages with system prompt + history + current user message
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-(MAX_HISTORY * 2):])  # Keep last N exchanges
    messages.append({"role": "user", "content": user_text})
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "model": "sarvam-30b",
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": 150,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {SARVAM_API_KEY}",
            "Content-Type": "application/json",
        }
        
        # Stream the LLM response for faster time-to-first-token
        async with client.stream(
            "POST",
            f"{SARVAM_BASE}/v1/chat/completions",
            json=payload,
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            
            full_response = []
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        import json
                        chunk = json.loads(data)
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            full_response.append(content)
                    except:
                        pass
            
            response_text = "".join(full_response)
            
            # Update conversation memory
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
            "speaker": SPEAKER_MAP.get(language_code, "shubh"),
            "output_audio_codec": "mp3",
            "pace": 1.1,  # Slightly faster for better demo feel
        }
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
                raise HTTPException(status_code=500, detail=f"TTS error: {error_text.decode()}")
            
            chunk_count = 0
            async for chunk in resp.aiter_bytes():
                chunk_count += 1
                yield chunk
            
            logger.info(f"TTS stream complete: {chunk_count} chunks")


@app.post("/talk")
async def talk(
    audio: UploadFile = File(...),
    language: str = Form("en"),
    session_id: str = Form(""),
):
    """Main demo endpoint: audio in → AI voice out (streaming)."""
    logger.info(f"Talk request: language={language}, session={session_id}, content_type={audio.content_type}")
    
    if not audio.content_type or not audio.content_type.startswith("audio"):
        raise HTTPException(status_code=400, detail="Audio file required")

    language_code = LANGUAGE_MAP.get(language, "en-IN")
    
    # Generate session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())

    try:
        # 1. STT — speech to text
        audio_bytes = await audio.read()
        logger.info(f"Audio size: {len(audio_bytes)} bytes")
        user_text = await stt(audio_bytes, language_code)

        if not user_text.strip():
            raise HTTPException(status_code=400, detail="No speech detected")

        # 2. LLM — generate response with conversation memory
        logger.info(f"User text: {user_text[:100]}")
        response_text = await llm(user_text, language_code, session_id)
        logger.info(f"LLM response: {response_text[:100]}")

        # 3. TTS — stream audio back
        logger.info("Starting TTS stream...")
        return StreamingResponse(
            tts_stream(response_text, language_code),
            media_type="audio/mpeg",
            headers={"X-Session-ID": session_id},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Talk endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok", "service": "buoyancy-voice-demo"}


@app.post("/clear-session")
async def clear_session(session_id: str = Form("")):
    """Clear conversation memory for a session."""
    if session_id and session_id in sessions:
        del sessions[session_id]
        return {"status": "cleared", "session_id": session_id}
    return {"status": "no session found"}
