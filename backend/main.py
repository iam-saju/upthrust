import os
import base64
import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

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
SYSTEM_PROMPT = """You are RA-1, a warm, helpful, and respectful voice customer support agent from Buoyancy Labs.

Your personality:
- Speak naturally like a friendly Indian customer support executive
- Be polite, patient, and solution-oriented
- Use simple, clear language
- Show empathy when the customer is frustrated
- Keep answers concise but helpful (avoid long replies)
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


async def stt(audio_bytes: bytes, language_code: str) -> str:
    """Send audio to Sarvam STT, return transcribed text."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        files = {"file": ("audio.webm", audio_bytes, "audio/webm")}
        data = {
            "model": "saaras:v3",
            "mode": "transcribe",
            "language_code": language_code,
        }
        headers = {"api-subscription-key": SARVAM_API_KEY}
        resp = await client.post(
            f"{SARVAM_BASE}/speech-to-text",
            files=files,
            data=data,
            headers=headers,
        )
        resp.raise_for_status()
        result = resp.json()
        return result.get("transcript", "")


async def llm(user_text: str, language_code: str) -> str:
    """Send text to Sarvam-30B LLM, return response."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "model": "sarvam-30b",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.7,
            "max_tokens": 300,
        }
        headers = {
            "Authorization": f"Bearer {SARVAM_API_KEY}",
            "Content-Type": "application/json",
        }
        resp = await client.post(
            f"{SARVAM_BASE}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def tts(text: str, language_code: str) -> bytes:
    """Send text to Sarvam TTS, return audio bytes (WAV)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "text": text,
            "model": "bulbul:v3",
            "target_language_code": language_code,
            "speaker": SPEAKER_MAP.get(language_code, "shubh"),
        }
        headers = {
            "api-subscription-key": SARVAM_API_KEY,
            "Content-Type": "application/json",
        }
        resp = await client.post(
            f"{SARVAM_BASE}/text-to-speech",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        audio_b64 = resp.json()["audios"][0]
        return base64.b64decode(audio_b64)


@app.post("/talk")
async def talk(
    audio: UploadFile = File(...),
    language: str = Form("en"),
):
    """Main demo endpoint: audio in → AI voice out."""
    if not audio.content_type or not audio.content_type.startswith("audio"):
        raise HTTPException(status_code=400, detail="Audio file required")

    language_code = LANGUAGE_MAP.get(language, "en-IN")

    # 1. STT — speech to text
    audio_bytes = await audio.read()
    user_text = await stt(audio_bytes, language_code)

    if not user_text.strip():
        raise HTTPException(status_code=400, detail="No speech detected")

    # 2. LLM — generate response
    response_text = await llm(user_text, language_code)

    # 3. TTS — text to speech
    audio_response = await tts(response_text, language_code)

    return Response(content=audio_response, media_type="audio/wav")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "buoyancy-voice-demo"}
