# 0007 — Hardware Abstraction Layer

**Status:** Accepted

## Context
The application depends on Pi-specific hardware, and the supported HATs differ in their LED control mechanism, ALSA card name, and available peripherals. Any SBC can be paired with any supported HAT:

| HAT | Button | LED control | ALSA card | Speaker |
|---|---|---|---|---|
| ReSpeaker | GPIO17 | APA102 via SPI | `seeed-2mic-voicecard` | No |
| Whisplay | GPIO17 | Discrete GPIO (GPIO23/24/25) | `wm8960soundcard` | Yes (8Ω 1W) |

Without abstraction, the full application cannot run or be tested on a development machine, and supporting multiple hardware combinations would require scattered conditionals throughout the codebase.

## Decision
Hardware-specific components are implemented behind interfaces. The active HAT implementation is selected at startup based on `hardware.hat` in `config.toml`.

Interfaces:
- `ButtonInterface` — detects button press and hold events
- `LEDInterface` — controls LED colour and pattern
- `AudioCaptureInterface` — captures audio from the microphone
- `DisplayInterface` — renders state, logo, and data on the LCD (no-op on HATs without a display)

Each interface has two implementations:
- **Real** — uses the actual Pi hardware (GPIO, SPI, ALSA)
- **Stub** — in-memory/no-op implementation for local development and testing

`DisplayInterface` is always present in the application; on the ReSpeaker HAT, the real implementation is a no-op. `AudioOutputInterface` (speaker) is planned for v2.

## Consequences
- The full application logic and encoding pipeline can be developed and tested locally without a Pi.
- Adding a new HAT requires only a new set of implementations — no changes to application logic.
- The active HAT is determined by config, not by runtime detection, keeping startup simple.
- Integration testing against real hardware still requires a Pi.
