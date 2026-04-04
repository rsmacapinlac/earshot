# 0009 — ASCII Art for LCD Display Rendering

**Status:** Accepted

## Context

The Whisplay HAT includes a 1.69" LCD (240×280px, ST7789P3). A rendering approach is needed for displaying device state, logo, and animations on this screen.

Options considered:

| Option | Asset files | Works in terminal | Works in README | Animation complexity |
|---|---|---|---|---|
| Pixel art sprites | Yes (PNG/BMP per frame) | No | No | High (frame images) |
| Vector / SVG | Yes | No | No | High |
| ASCII art (monospace font) | No | Yes | Yes | Low (string constants) |

The device has no graphical desktop — all interaction is headless. The primary development and debugging surface is the terminal. A rendering approach that works identically on the LCD, in a terminal (stub mode), in the GitHub README, and on a future website is strongly preferred.

## Decision

Render all display content — logo, animations, state labels, and data — as ASCII art using a monospace font. The logo and animation frames are stored as plain string constants in the application. No external image assets are required.

The logo is a radiating arc mark:

```
·
 )
 ))   EARSHOT
 )))
 ))
 )
·
```

Animations are achieved by cycling between string frames at the LED's rhythm (~1 second cycle), keeping animation logic trivially simple.

## Consequences

- No asset pipeline, no image files, no build step for graphics.
- The Stub `DisplayInterface` implementation prints ASCII frames to stdout — the display is fully observable during local development without a Pi.
- The same logo and character representation is used in the GitHub README (code block) and can be CSS-styled on a website.
- Display resolution constrains art to roughly 30 columns × 35 rows at a readable font size — sufficient for the logo and text zones defined in `display.md`.
- Complex graphics or images are not possible. This is an acceptable trade-off given the device's headless, utilitarian nature.
