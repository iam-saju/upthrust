# Buoyancy Labs Voice Demo Backend

FastAPI backend for the in-browser voice AI demo. Connects to Sarvam AI for STT, LLM, and TTS.

## Local Development

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your SARVAM_API_KEY

uvicorn main:app --reload --port 8000
```

## Railway Deployment

1. Push this repo to GitHub
2. On Railway, create a new project → Deploy from GitHub
3. Select the `backend` directory as the root
4. Add environment variables:
   - `SARVAM_API_KEY` — your Sarvam API key
   - `ALLOWED_ORIGIN` — your Netlify URL (e.g., `https://buoyancy.netlify.app`)
5. Deploy

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/talk` | Send audio + language → receive AI voice response |
| GET | `/health` | Health check |

## Demo Flow

1. User speaks into browser mic (MediaRecorder → webm)
2. Audio sent to `/talk` with language code
3. Backend: STT → LLM → TTS pipeline
4. WAV audio returned to browser for playback
