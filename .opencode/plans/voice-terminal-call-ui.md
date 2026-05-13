# RA-1 Voice Terminal — Phone Call UI Redesign

## Model Shift
From ambient inline text → phone call UI with small circle buttons.

---

## Spec (Confirmed)

### Default State
- **Green circle**: 42px diameter, flat fill
- **Color**: `#6a9e6a` (muted sage, intentional but not WhatsApp)
- **Icon**: Dial/phone icon inside
- **Text**: "Call RA-1" next to circle, vertically centered, body font
- **Label below**: "RA-1 · Beta Voice Agent"

### Active State
- **Red circle**: same 42px, muted red fill
- **Icon**: Hang-up handset (rotated)
- **Animation**: Expanding ripple ring around the button — low opacity, slow expand-and-fade
- **Button stays still** (stability signal)
- **Label below**: "RA-1 · listening..." or "RA-1 · connected"

### Constraints
- No transcript (stripped down)
- No border on circles (flat fill only)
- No chat bubbles
- Small — doesn't dominate section

---

## Files
| File | Action |
|------|--------|
| `src/components/voice-terminal.tsx` | Complete rewrite |

---

## Animation Details
- **Ripple**: CSS `::after` pseudo-element, `scale(1)` → `scale(2.5)`, opacity `0.3` → `0`, 2s duration
- **Stagger**: Multiple ripples with 0.6s delay between them
- **Button**: No pulse, no movement — stable center

## Colors
- **Idle green**: `#6a9e6a`
- **Active red**: `#c46a6a` (muted coral)
- **Ripple**: Same color as button, 15% opacity
- **Text**: `neutral-400` for label, `neutral-500` for "Call RA-1"
