# Development Workflow

## Overview

Earshot has two distinct development contexts:

| Layer | Hardware required | Where to develop |
|---|---|---|
| Encoding pipeline (WAV → Opus) | No | Local dev machine |
| Hardware (GPIO, LED, audio capture, display) | Yes (or stubbed) | Local with stubs / Pi for integration |

---

## Local Development

### Encoding Pipeline
ffmpeg-based WAV-to-Opus encoding is hardware-agnostic and runs on any Linux/Mac/Windows machine. Develop and test encoding logic locally using sample audio files.

### Hardware Abstraction
Hardware-specific components are implemented behind interfaces (see ADR-0007). Each interface has a **Real** implementation (Pi hardware) and a **Stub** implementation (in-memory/no-op for local development).

| Interface | Responsibility | Stub behaviour |
|---|---|---|
| `ButtonInterface` | Button press and hold detection | Simulates events via keyboard or test input |
| `LEDInterface` | LED colour and pattern control | Logs colour/pattern to stdout |
| `AudioCaptureInterface` | Microphone audio capture via ALSA | Reads from a fixture WAV file |
| `AudioOutputInterface` | Speaker output (Whisplay HAT only) | No-op |
| `DisplayInterface` | LCD display rendering (Whisplay HAT only) | Prints ASCII frames to stdout |

The active HAT implementation is selected at startup based on `hardware.hat` in `config.toml`. Pass `--stub` to force stub implementations regardless of environment:

```bash
python -m earshot --stub
```

This is the standard way to run the application on a development machine without a Pi.

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
2. Develop application logic against stub hardware interfaces
3. Push to the Pi and run `sudo systemctl restart earshot` for hardware integration testing
4. Capture any new edge-case recordings as fixtures

---

## Target Hardware

| Config | SBC | HAT |
|---|---|---|
| Desk | Pi 4B | ReSpeaker 2-Mic or Whisplay |
| Portable | Pi Zero 2W | Whisplay |

See [hardware.md](requirements/hardware.md) for full component details.
