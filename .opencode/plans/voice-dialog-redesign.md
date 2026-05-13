# RA-1 Voice Dialog — ElevenLabs-Inspired Redesign

## Goal
Replace the inline pill component with a floating dialog containing an animated orb, language selector, and clean status labels.

---

## Architecture

### State Machine
```
[Page: Green circle trigger]
         ↓ click
[Dialog: idle] → [listening] → [speaking] → [idle]
         ↓ end call
[Page: Green circle trigger]
```

### Files
| File | Action |
|------|--------|
| `src/components/voice-terminal.tsx` | Complete rewrite — dialog + orb + dropdown |
| `src/components/voice-orb.tsx` | New — animated orb component (optional separation) |
| `src/app/page.tsx` | Update trigger placement |

---

## Component Structure

### 1. Trigger (on page)
- Existing 42px green circle (`#7a9e7a`)
- Opens dialog on click
- Disappears or dims when dialog is open

### 2. Dialog Card
```
width: 340px
background: #ffffff
border: 1px solid #e5e5e5
border-radius: 12px
box-shadow: 0 4px 24px rgba(0,0,0,0.06)
position: fixed (or absolute within section)
padding: 24px
```

**Close behaviors:**
- Click × icon inside dialog
- Click outside dialog (overlay backdrop)
- Call ends naturally

### 3. Top Bar
```
Left:  "RA-1 · Beta Voice Agent"  (muted gray, 11px)
Right: [🇮🇳 Hindi ▼]              (dropdown)
```

**Dropdown contents:**
```
🇮🇳 Hindi
🇮🇳 Bengali
🇮🇳 Tamil
🇮🇳 Telugu
🇮🇳 Kannada
🇮🇳 Malayalam
🇮🇳 Marathi
─────────────────
🇬🇧 English
```

- Default: Hindi
- Store selected language in component state
- Pass to voice SDK on call start
- Divider before English (thin `rgba(0,0,0,0.08)`)

### 4. The Orb
```
diameter: 120px
border-radius: 50%
position: center of dialog
```

**Gradient (warm earthy):**
```css
background: radial-gradient(
  circle at 35% 35%,
  #e8c97a 0%,    /* light ochre highlight */
  #c97a3a 40%,   /* warm amber */
  #8b4a1a 100%   /* dusty terracotta */
);
```

**Three animation states:**

| State | CSS Class | Animation |
|-------|-----------|-----------|
| Idle | `.orb-idle` | Static, no animation |
| Listening | `.orb-listening` | Slow gentle pulse, scale(1) → scale(1.04), 1.5s ease-in-out |
| Speaking | `.orb-speaking` | Active morphing — subtle ripple/shimmer, faster |

**Implementation:** Pure CSS `@keyframes`. No library.

```css
@keyframes orb-listen {
  0%, 100% { transform: scale(1); opacity: 0.9; }
  50% { transform: scale(1.04); opacity: 1; }
}

@keyframes orb-speak {
  0% { transform: scale(1) rotate(0deg); }
  25% { transform: scale(1.02) rotate(0.5deg); }
  50% { transform: scale(1.04) rotate(0deg); }
  75% { transform: scale(1.02) rotate(-0.5deg); }
  100% { transform: scale(1) rotate(0deg); }
}
```

### 5. Status Text
Centered below orb. 12px, muted gray.

```
Idle:     "Tap to start"
Listen:   "Listening..."
Speak:    "Speaking..."
End:      "Call ended"
```

### 6. End Call
Small icon, bottom-right corner of dialog.

```
Position: absolute, bottom: 16px, right: 16px
Size: 24px
Icon: × (close) or muted red phone-hangup
Opacity: 0.4 → 0.7 on hover
No button background — just the icon
```

### 7. Backdrop (optional)
If dialog is `position: fixed`, add a subtle backdrop:
```css
background: rgba(255,255,255,0.4);
backdrop-filter: blur(2px);
```
Clicking backdrop closes dialog.

---

## Language Array

```tsx
const LANGUAGES = [
  { code: "hi-IN", label: "Hindi", flag: "🇮🇳" },
  { code: "bn-IN", label: "Bengali", flag: "🇮🇳" },
  { code: "ta-IN", label: "Tamil", flag: "🇮🇳" },
  { code: "te-IN", label: "Telugu", flag: "🇮🇳" },
  { code: "kn-IN", label: "Kannada", flag: "🇮🇳" },
  { code: "ml-IN", label: "Malayalam", flag: "🇮🇳" },
  { code: "mr-IN", label: "Marathi", flag: "🇮🇳" },
  { code: "en-IN", label: "English", flag: "🇬🇧" },
];
```

---

## Interaction Flow

1. **User clicks green circle trigger**
   - Dialog opens (fade in, 200ms)
   - Green trigger hides or dims

2. **User taps orb or a "Start" area**
   - State: idle → listening
   - Orb animates (listening pulse)
   - Status: "Listening..."
   - Mic opens, VAD begins

3. **User speaks, silence detected**
   - State: listening → processing → speaking
   - Audio sent to backend
   - Orb: speaking animation
   - Status: "Speaking..."
   - TTS response plays

4. **TTS ends**
   - State: speaking → listening
   - Auto-loop back to listening

5. **User clicks × or outside**
   - State: any → idle
   - Dialog closes
   - Green trigger reappears
   - Cleanup: stop mic, stop audio

---

## Open Questions

1. **Dialog position**: Fixed to viewport (bottom-right like ElevenLabs) or absolute within the Agents section?

2. **Backdrop**: Do we want the blurred overlay, or should the dialog float without dimming the page?

3. **Transcript in dialog**: The spec says no transcript, but should we show the current utterance (what the user just said) as temporary text inside the dialog? Or keep it completely voice-only?

4. **Language flags**: Use emoji flags (🇮🇳) or avoid flags entirely (just text)? Flags can be politically sensitive in India.

5. **Orb click to start**: Should tapping the orb itself start the call, or should there be a separate "Start" button/area?

---

## Implementation Estimate

- Dialog structure: 30 min
- Orb + animations: 45 min
- Language dropdown: 30 min
- State machine + voice integration: 30 min
- Polish (shadows, transitions, positioning): 30 min

**Total: ~2.5–3 hours**
