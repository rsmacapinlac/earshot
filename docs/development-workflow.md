# Development Workflow

## Overview

Earshot has two distinct development contexts:

| Layer | Hardware required | Where to develop |
|---|---|---|
| Encoding pipeline (WAV → Opus) | No | Local dev machine |
| Hardware (GPIO, LED, audio capture) | Yes (or mocked) | Local with mocks / Pi for integration |

---

## Local Development

### Encoding Pipeline
ffmpeg-based WAV-to-Opus encoding is hardware-agnostic and runs on any Linux/Mac/Windows machine. Develop and test encoding logic locally using sample audio files.

### Hardware Abstraction
Hardware-specific components (button, LED, audio capture) are implemented behind interfaces:

- `ButtonInterface` — detects press events
- `LEDInterface` — controls LED colour and pattern
- `AudioInterface` — captures audio from the microphone

Locally, stub implementations are used in place of the real GPIO/SPI/ALSA drivers, allowing the full application logic to run and be tested without a Pi.

---

## Deploying to the Pi

```bash
git pull
sudo systemctl restart earshot
```

---

## Test Fixtures

Maintain a small set of real recordings in `tests/fixtures/` as regression fixtures for the encoding pipeline. These should cover:
- Short recordings (near the 3-second minimum)
- Full-length chunks (15 minutes)
- Recordings that trigger encoding failure paths

---

## Iteration Cycle

1. Develop and test encoding logic locally against fixture audio files
2. Develop application logic against mock hardware interfaces
3. Push to the Pi and run `sudo systemctl restart earshot` for hardware integration testing
4. Capture any new edge-case recordings as fixtures
