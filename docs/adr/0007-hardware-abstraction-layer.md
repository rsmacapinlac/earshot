# 0007 — Hardware Abstraction Layer

**Status:** Accepted

## Context
The application depends on Pi-specific hardware: a GPIO button, an SPI-controlled APA102 LED, and ALSA audio capture via the ReSpeaker HAT. Without abstraction, the full application cannot run or be tested on a development machine.

## Decision
Hardware-specific components are implemented behind interfaces:

- `ButtonInterface` — detects button press events
- `LEDInterface` — controls LED colour and pattern
- `AudioInterface` — captures audio from the microphone

Two implementations exist for each:
- **Real** — uses the actual Pi hardware (GPIO, SPI, ALSA)
- **Stub** — in-memory/no-op implementation for local development and testing

## Consequences
- The full application logic and encoding pipeline can be developed and tested locally without a Pi.
- The encoding pipeline is inherently hardware-agnostic and benefits most from this.
- Adds a small amount of structural overhead, justified by the development velocity gain.
- Integration testing against real hardware still requires a Pi.
