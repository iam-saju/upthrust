# Real-Time Continuous Voice Call - Implementation Plan

## Overview
Transform the current start-stop voice demo into a continuous, real-time call experience with VAD (Voice Activity Detection), auto-loop, and tap-to-interrupt.

---

## Changes Required

### 1. Backend: `backend/main.py`

**Line 7**: Add import for URL encoding:
```python
from urllib.parse import quote
```

**Lines 23-28**: Update CORS middleware to expose custom headers:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGIN", "*")],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID", "X-User-Text", "X-Agent-Text"],
)
```

**Lines 243-247**: Update StreamingResponse headers to include Unicode-safe text:
```python
return StreamingResponse(
    tts_stream(response_text, language_code),
    media_type="audio/mpeg",
    headers={
        "X-Session-ID": session_id,
        "X-User-Text": quote(user_text),
        "X-Agent-Text": quote(response_text),
    },
)
```

---

### 2. Frontend: `src/components/voice-widget.tsx`

Complete rewrite with:

**State Machine**:
- `idle` → `listening` → `processing` → `speaking` → `listening` (loop)

**VAD Implementation** (~30 lines):
- Use `AnalyserNode` with `fftSize: 2048`
- Monitor RMS audio level every animation frame
- Threshold: `0.02` for silence detection
- Silence duration: `1.5 seconds` before auto-trigger
- Minimum speech: `400ms` to avoid false triggers on noise

**Key Functions**:
- `startListening()` - Opens mic, starts VAD loop
- `checkSilence()` - RAF loop monitoring RMS levels
- `stopRecording()` - Stops mic, sends audio to backend
- `sendToBackend()` - Records audio blob, POSTs to `/talk`
- `playAudio()` - Plays TTS response, auto-triggers `startListening()` on end
- `interrupt()` - Stops playback, jumps to listening

**UI Components**:
- Central orb (192px) with color-coded states:
  - Grey (idle)
  - Purple pulse + expanding rings (listening)
  - Amber glow + spinner (processing)
  - Teal glow (speaking)
- VAD progress bar at bottom of orb (fills over 1.5s silence)
- Text display area showing user/agent transcription
- Hang Up button (red)
- Status text below button

**Interrupt**: Click orb or waveform area while `speaking` → stops audio → `startListening()`

---

## Files to Modify

| File | Changes |
|------|---------|
| `backend/main.py` | Add `quote` import, expose headers in CORS, add text headers to response |
| `src/components/voice-widget.tsx` | Complete rewrite with VAD, state machine, continuous loop |

---

## Testing Checklist

- [ ] VAD triggers after 1.5s silence (not too early, not too late)
- [ ] Auto-loop works: speak → process → speak → auto-listen again
- [ ] Tap-to-interrupt works while AI is speaking
- [ ] Hindi/Malayalam text displays correctly (Unicode headers)
- [ ] Hang Up properly cleans up all resources
- [ ] No memory leaks from RAF loops or AudioContext
