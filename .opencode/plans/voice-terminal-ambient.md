# RA-1 Voice Terminal — Ambient Inline Redesign

## Core Insight
The voice should feel already present, ambient, waiting — not like a button to activate something. The interaction point should feel like the site talking to you.

---

## Changes

### 1. Default State (No Button)
Replace pill button with plain inline text:

```
RA-1 is listening — ▏▏▏
```

- "RA-1 is listening —" in same muted gray as section labels (like "Our Belief")
- 3-4 thin vertical bars after the em-dash, very subtle, slow pulse
- No border, no background, no icon, no pill shape
- Flush with body copy column
- Same font/size as body text

### 2. Active State
When clicked, expand slightly:

```
RA-1 · listening

▁▂▃▄▃▂▁
```

- "RA-1 · listening" in muted label style (same as "Our Belief")
- Waveform bars: smaller, more ambient, lower opacity
- No green tint background — use page background or barely-there off-white
- No container, no card, no border

### 3. Typography
- All text: same size as body text (15-16px), same weight
- "RA-1 · Beta Voice Agent" below in smaller muted text
- Should feel like a footnote that happens to be interactive, not a CTA

### 4. Placement
- Natural continuation of paragraph
- After "Just a voice that knows how to respond." → one line break → RA-1 line
- No visual island, no container

### 5. End Interaction
- Tiny "End call" text link, bottom-right
- Muted gray, no button shape

---

## Implementation

Rewrite `src/components/voice-terminal.tsx`:
1. Remove all button/pill styling
2. Use plain `<span>` and `<div>` elements
3. Subtle breathing animation on default state bars
4. Smaller, quieter waveform in active state
5. All typography matched to site's body text
6. No borders, no backgrounds, no containers

---

## Files
| File | Action |
|------|--------|
| `src/components/voice-terminal.tsx` | Complete rewrite |

---

## Notes
- Keep VAD logic (silence detection)
- Keep /greet endpoint flow
- Keep auto-loop after TTS
- Remove all waveform/AnalyserNode visual logic, replace with simpler CSS animations
