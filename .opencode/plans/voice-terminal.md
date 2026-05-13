# RA-1 Voice Panel - Embedded Narrative Layout

## Overview
Transform the floating voice widget into a centered, embedded "live conversational artifact" placed below the market image in the storytelling flow: belief → context → India visual → live voice demonstration.

---

## Page Flow

```
Support should sound like your shopkeeper picked up the call.
[ paragraph about Buoyancy Labs ]

[ market image - large, editorial, full width of content column ]

[ RA-1 Voice Panel - centered, max-width 520px ]
```

---

## Layout Changes: `src/app/page.tsx`

**Remove:**
- Floating `<VoiceWidget />` at bottom of page

**Add after documentary image (line 79):**
```tsx
{/* ── RA-1 Voice Panel ─────────────────────────────── */}
<div className="max-w-5xl mx-auto px-6 sm:px-10 md:px-14 lg:px-20 pt-8 pb-12">
  <div className="flex justify-center">
    <div className="w-full max-w-[520px]">
      <VoiceTerminal />
    </div>
  </div>
</div>
```

This keeps the panel inside the content column, centered, never touching screen edges.

---

## Component: `src/components/voice-terminal.tsx`

### Card Styling
```css
background: rgba(255, 255, 255, 0.55);
border: 1px solid rgba(0, 0, 0, 0.06);
backdrop-filter: blur(12px);
border-radius: 28px;
padding: 32px;
```

### Header
```
RA-1
Malayalam • Live
```
- "RA-1" — Space Grotesk, bold, 18px
- Language indicator — Inter, 12px, neutral-400
- Rotates every 3s when idle: Malayalam → Tamil → Hindi → Bengali → English → Tanglish → Manglish

### Orb
- 120px diameter
- Muted gradient (not neon)
- 6s breathing animation: subtle scale (1.0 → 1.04 → 1.0) + opacity pulse
- State colors (muted):
  - Idle: neutral-300
  - Listening: purple-400 (soft)
  - Processing: amber-400 (soft)
  - Speaking: teal-400 (soft)
- VAD progress bar: thin, subtle, at bottom of orb

### Transcript
- Customer: lighter gray (#6b7280), smaller (13px), right-aligned
- Agent: darker (#111827), stronger (14px), left-aligned
- Word-by-word reveal: 120ms per word, 400ms delay before agent
- Max height: 120px, scroll overflow
- Soft divider lines between exchanges

### Button
- Idle: "Start conversation" — minimal, neutral-900 bg, white text
- Active: "End conversation" — red-500 bg, white text
- No icons, no emojis

---

## State Machine

| State | Orb | Animation | Button | Status |
|-------|-----|-----------|--------|--------|
| idle | neutral-300 | breathe 6s | Start conversation | Tap to start |
| listening | purple-400 | soft rings | End conversation | Listening... |
| processing | amber-400 | spinner | End conversation | Thinking... |
| speaking | teal-400 | pulse | End conversation | Tap orb to interrupt |

---

## VAD (Preserved)
- `AnalyserNode` with `fftSize: 2048`
- RMS threshold: 0.02
- Silence duration: 1.5s
- Minimum speech: 400ms
- Auto-loop after TTS finishes
- Tap-to-interrupt on orb

---

## Language Rotation (Idle Only)
```tsx
const LANGUAGES = [
  "Malayalam", "Tamil", "Hindi", "Bengali", "English", "Tanglish", "Manglish"
];
```
- Rotates every 3s when `state === "idle"`
- Stops rotating once call starts
- Shows detected language during active call

---

## Files to Modify

| File | Action |
|------|--------|
| `src/app/page.tsx` | Remove floating widget, add embedded panel below image |
| `src/components/voice-terminal.tsx` | Create new component |
| `src/components/voice-widget.tsx` | Delete (replaced) |

---

## Testing Checklist

- [ ] Panel renders centered below image, max-width 520px
- [ ] Card has frosted glass effect (backdrop-filter blur)
- [ ] Language indicator rotates every 3s when idle
- [ ] Orb breathing animation is subtle (no neon)
- [ ] VAD triggers after 1.5s silence
- [ ] Auto-loop works
- [ ] Tap-to-interrupt works
- [ ] Transcript shows customer/agent with proper alignment
- [ ] Word-by-word reveal animation
- [ ] End conversation cleans up resources
- [ ] Panel never touches screen edges
- [ ] Responsive: maintains centering on mobile
