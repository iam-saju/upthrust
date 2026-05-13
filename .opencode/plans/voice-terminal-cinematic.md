# RA-1 Voice Terminal — Cinematic Conversation Redesign

## Problem Statement
Current implementation feels mechanical (waveform, status labels, equalizers). User wants human presence, not software interface.

## Core Principle
The interface IS the conversation. Not a control panel for it.

---

## New Interaction Flow

### 1. Idle State
```
Talk to RA-1 →
```
- Soft capsule, minimal border
- No icons, no gradients, no tech signals
- Arrow implies invitation, not button

### 2. Connecting (transient)
```
Connecting…
```
- Fades in for 1-2s
- Then transitions to active

### 3. Active State
```
RA-1 joined the call.

"Hi. How can I help you today?"
```
- Cinematic text reveal
- Each line fades in sequentially
- Soft, editorial typography

### 4. Listening
```
RA-1 is listening…

[user transcript appears here]
```
- User speech transcribed in real-time
- Appears as they speak
- Soft gray, right-aligned

### 5. Speaking / Response
```
[agent response fades in word by word]
```
- Word-by-word reveal
- 80ms per word
- Slight opacity gradient on new words

### 6. End
Tiny "End call" text link, bottom-right.
Muted. Almost hidden.

---

## Visual Design

### Container
- Same capsule shape (48px height idle)
- Active: expands to auto-height
- Background: white or `#fafaf9`
- Border: `1px solid rgba(0,0,0,0.06)`
- No shadows, no glow, no tech chrome

### Typography
- Agent text: `Inter` or editorial serif, 15px, warm gray
- User text: Same font, 14px, lighter gray, right-aligned
- State labels: `Space Grotesk`, 11px, tracking wide, very muted
- Conversation text is the hero, not the UI

### Animation
- Fade in: 400ms, ease-out
- Word reveal: 80ms stagger per word
- Typing cursor: subtle blinking `|` after "listening…"
- Breathing: very subtle opacity pulse on container (0.98 → 1.0)
- No waveform, no bars, no equalizer

### End Call
- Tiny text link: "End call"
- Positioned bottom-right
- `rgba(0,0,0,0.25)` color
- Hover: `rgba(0,0,0,0.5)`
- No button shape, no icon

---

## Files to Modify

| File | Action |
|------|--------|
| `src/components/voice-terminal.tsx` | Complete rewrite |

---

## Implementation Notes

1. Remove all waveform/AnalyserNode logic
2. Keep VAD for silence detection (still needed to trigger send)
3. Add word-by-word reveal animation for agent responses
4. Add typing cursor animation for listening state
5. Sequential fade-in for multi-line content
6. Minimal state: idle → connecting → active/listening/speaking

---

## Key Decision: Should we keep STT streaming or batch?

Options:
- **Batch**: Wait for silence, then show full transcript at once (simpler, cleaner)
- **Streaming**: Show words as they come (more alive, but riskier)

Recommendation: **Batch** — shows cleaner in editorial layout. The silence itself creates pause/drama.

---

## Critical: What happens to the /greet endpoint?

Keep it. On first click:
1. Show "Connecting…"
2. Fetch greet audio
3. Show "RA-1 joined the call." + greeting text
4. Play audio
5. Transition to listening

The greeting text should fade in word by word as audio plays.

---

## Success Criteria
- [ ] Component feels like reading a conversation, not using software
- [ ] No waveform, no equalizer, no status indicators
- [ ] Text is the primary visual element
- [ ] Animations feel cinematic, not mechanical
- [ ] End call is barely visible
- [ ] Typography matches editorial aesthetic
