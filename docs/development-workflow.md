# Development Workflow

## Overview

Earshot has two distinct development contexts:

| Layer | Hardware required | Where to develop |
|---|---|---|
| Processing (diarization + transcription) | No | Local dev machine |
| Hardware (GPIO, LED, audio capture) | Yes (or mocked) | Local with mocks / Pi for integration |

---

## Local Development

### Processing Pipeline
Whisper and pyannote.audio are hardware-agnostic and run on any Linux/Mac/Windows machine. Develop and test the processing pipeline locally using sample audio files for fast iteration.

### Hardware Abstraction
Hardware-specific components (button, LED, audio capture) are implemented behind interfaces:

- `ButtonInterface` — detects press events
- `LEDInterface` — controls LED colour and pattern
- `AudioInterface` — captures audio from the microphone

Locally, stub implementations are used in place of the real GPIO/SPI/ALSA drivers, allowing the full application logic to run and be tested without a Pi.

### Hugging Face Setup
pyannote.audio uses gated models that require a one-time setup:
1. Create a [Hugging Face](https://huggingface.co) account
2. Accept the terms for the pyannote models
3. Generate an access token and set it as `HF_TOKEN` in your environment

---

## Deploying to the Pi

```bash
git pull
sudo systemctl restart earshot
```

---

## Test Fixtures

Maintain a small set of real recordings in `tests/fixtures/` as regression fixtures for the processing pipeline. These should cover:
- Single speaker
- Two speakers
- Three or more speakers
- Background noise / short silences

---

## Iteration Cycle

1. Develop and test processing logic locally against fixture audio files
2. Develop application logic against mock hardware interfaces
3. Push to the Pi and run `sudo systemctl restart earshot` for hardware integration testing
4. Capture any new edge-case recordings as fixtures
