# Display (Whisplay HAT LCD)

> State definitions, LED colours, and button behaviour are in [device-state.md](device-state.md). This document specifies the corresponding LCD display behaviour for each state.

The Whisplay HAT includes a 1.69" LCD (240×280px, ST7789P3, SPI). This display is available on the Whisplay HAT only — on the ReSpeaker HAT, all display interface calls are no-ops.

---

## Design Principles

1. **The LED is primary.** The LCD is supplementary — it adds context the LED cannot convey (labels, timers, counts).
2. **Accent colour mirrors the LED.** Every screen uses the current state's LED colour as its accent.
3. **The logo expresses activity.** The radiating arc logo is the visual centre of every screen. Its animation directly reflects device activity — more arcs, more active.
4. **Animations mirror the LED pattern.** In pulsating LED states, the logo animates in sync (~1 second cycle). In solid LED states, the logo is static.
5. **Glanceable first.** The most important information must be readable in under one second at arm's length.
6. **Dark background throughout.** Near-black (`#0D0D0D`) on all screens.

---

## Colour Palette

| State | Accent colour | Hex |
|---|---|---|
| Booting | White | `#FFFFFF` |
| Ready / idle | Green | `#00CC44` |
| Recording | Red | `#FF3030` |
| Encoding | Blue | `#2080FF` |
| Encoding failure | Red | `#FF3030` |
| USB transfer | Blue | `#2080FF` |
| USB transfer complete | Blue | `#2080FF` |
| USB transfer error | Orange | `#FF8000` |
| Disk threshold reached | Orange | `#FF8000` |
| Transcribing | Amber | `#FFB300` |
| Shutting down | White | `#FFFFFF` |
| Background (all states) | Near-black | `#0D0D0D` |

---

## The Logo

The Earshot logo is a radiating arc mark — a dot with concentric arcs opening to the right, representing sound propagating outward. It is rendered in ASCII using a monospace font.

### Canonical mark (standalone):

```
·
 )
 ))
 )))
 ))
 )
·
```

### Full logo (mark + wordmark):

```
·
 )
 ))   EARSHOT
 )))
 ))
 )
·
```

### Compact / inline:

```
·))) EARSHOT
```

The logo is rendered in the current state's accent colour. On the LCD the wordmark is omitted — the mark alone is used, centred in Zone B.

### Logo Animation

The logo animates by building and collapsing the arcs outward, creating a pulse that mirrors the LED rhythm. Each frame is a complete ASCII redraw of Zone B.

| Frame | Content | Notes |
|---|---|---|
| 1 | `·` (dot only) | Minimum — silence, rest |
| 2 | `· )` | One arc |
| 3 | `· ))` | Two arcs |
| 4 | `· )))` | Three arcs — maximum |
| 3 | `· ))` | Collapsing |
| 2 | `· )` | Collapsing |
| 1 | `·` | Back to rest |

In pulsating states the full cycle runs once per ~1 second, in sync with the LED. In solid states (idle) the logo holds at frame 4 (full arcs), static.

On boot, the arcs **build in** from frame 1 → 4 (one-shot, ~2 seconds). On shutdown, the arcs **collapse out** from frame 4 → 1 in sync with the LED fade-to-off.

---

## Layout

```
┌──────────────────────────┐
│                          │
│      [ STATE LABEL ]     │  Zone A — ~60px  (bold, accent colour)
│                          │
│        [ LOGO ]          │  Zone B — ~120px (arc mark, centred)
│                          │
│      [ PRIMARY DATA ]    │  Zone C — ~60px  (large, white or accent)
│     [ SECONDARY DATA ]   │  Zone D — ~40px  (small, muted #888888)
│                          │
└──────────────────────────┘
```

---

## Screens by State

### Booting

| Zone | Content |
|---|---|
| A | `EARSHOT` — white |
| B | Logo: arcs build in from frame 1 → 4 (one-shot) |
| C | `Starting...` animated ellipsis |
| D | Version number (e.g. `v0.1`) |

---

### Ready / Idle

| Zone | Content |
|---|---|
| A | `READY` — green |
| B | Logo: full arcs (frame 4), static |
| C | Current time `HH:MM` |
| D | `N sessions  ·  NN% disk` |

---

### Recording

| Zone | Content |
|---|---|
| A | `● REC` — red; `●` pulses with LED |
| B | Logo: full pulse animation, synced to LED |
| C | Session timer `HH:MM:SS` — counts up |
| D | `Chunk N  ·  NN% disk` |

**If USB host connection is detected while recording** (FR-12 deferred offload):

| Zone | Content |
|---|---|
| D | `USB pending  ·  Chunk N` |

---

### Encoding

| Zone | Content |
|---|---|
| A | `ENCODING` — blue |
| B | Logo: pulse animation, synced to LED |
| C | `Chunk N of N` |
| D | `NN% disk` |

---

### Encoding Failure

| Zone | Content |
|---|---|
| A | `ENCODE FAILED` — red |
| B | Logo: single dot only (frame 1), static |
| C | `Chunk N could not encode` |
| D | `WAV file retained` |

Duration: matches the LED fast-blink (×3), then transitions to Ready. Logo rebuilds to frame 4 on exit.

---

### USB Transfer (in progress)

| Zone | Content |
|---|---|
| A | `TRANSFER` — blue |
| B | Logo: pulse animation, synced to LED |
| C | `N of N sessions` |
| D | `NN% disk` |

---

### USB Transfer Complete

| Zone | Content |
|---|---|
| A | `DONE` — blue |
| B | Logo: full arcs (frame 4), static |
| C | `N sessions moved` |
| D | `Safe to remove` |

Duration: 2–3 seconds, then transitions to Ready.

---

### USB Transfer Error

| Zone | Content |
|---|---|
| A | `TRANSFER ERROR` — orange |
| B | Logo: single dot (frame 1), static |
| C | Error reason (e.g. `Stick full`) |
| D | `Remove stick to continue` |

---

### Disk Threshold Reached

| Zone | Content |
|---|---|
| A | `STORAGE FULL` — orange |
| B | Logo: pulse animation, synced to LED |
| C | `NN% used` |
| D | `Remove files to record` |

---

### Transcribing

Only shown when `transcription.enabled = true` and the transcription queue is non-empty.

| Zone | Content |
|---|---|
| A | `TRANSCRIBING` — amber |
| B | Logo: pulse animation, synced to LED |
| C | `Session N of N` — queue position (e.g. `Session 1 of 3`) |
| D | Session timestamp (e.g. `2026-04-03 14:22`) |

On completion of the full queue, a brief confirmation screen is shown before returning to idle:

| Zone | Content |
|---|---|
| A | `DONE` — amber |
| B | Logo: full arcs (frame 4), static |
| C | `Transcription complete` |
| D | `N sessions processed` |

Duration: 3 seconds, then transitions to Ready.

---

### Shutting Down

| Zone | Content |
|---|---|
| A | `GOODBYE` — white |
| B | Logo: arcs collapse from frame 4 → 1, synced to LED fade |
| C | `Safe to unplug soon` |
| D | *(blank)* |

---

## Logo as Brand Asset

The ASCII mark works across all surfaces without image assets:

| Surface | Usage |
|---|---|
| LCD display | Animated, accent-coloured, centred in Zone B |
| Terminal | Printed at startup and in dev/stub mode |
| GitHub README | Code block in the header |
| Website | Rendered in a monospace font block; CSS-coloured per context |

The canonical brand representation is the full logo (mark + wordmark). The standalone mark is used where space is constrained.

---

## FR-13: Display Interface

- The display is driven via `DisplayInterface`, consistent with the HAL pattern (ADR-0003).
- Two implementations: **Real** (ST7789P3 via SPI) and **Stub** (prints logo and state to stdout, for development).
- The logo frames are stored as plain string constants — no external asset files.
- The display renders using a monospace font. Font size is chosen so the 5-character wide mark fits comfortably centred in Zone B.
- The display is updated on every state transition. Zone C and Zone D refresh on a timer (session timer: every second; disk usage: every 10 seconds).
- Display brightness is configurable via `display.brightness` in `config.toml` (0–100, default: 80).
- Setting `display.brightness = 0` turns the backlight off entirely — useful for covert or low-power operation.
