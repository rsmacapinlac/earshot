# Hardware

## Single Board Computer

| | Minimum | Recommended |
|---|---|---|
| Model | Raspberry Pi 4B 2GB | Raspberry Pi 4B 4GB |
| RAM | 2GB | 4GB |
| CPU | Cortex-A72 (1.5GHz quad-core) | Cortex-A72 (1.5GHz quad-core) |
| OS | Raspberry Pi OS Lite 64-bit | Raspberry Pi OS Lite 64-bit |

> **Note:** Pi 3B/3B+ (1GB) and Pi Zero 2W are not supported — insufficient RAM for on-device Whisper + diarization. Pi 5 compatibility is untested.

## Audio HAT

| Component | Detail |
|---|---|
| Audio HAT | Seeed ReSpeaker 2-Mic Pi HAT |
| Microphones | 2x onboard MEMS mics |
| LED | APA102 RGB LEDs x3 (onboard HAT, controlled via SPI) — 1 used, v1 |
| Button | User button on GPIO17 (onboard HAT) |
