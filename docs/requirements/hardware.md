# Hardware

## Single Board Computers

Earshot supports two SBCs with the ReSpeaker HAT.

| | Pi 4B | Pi Zero 2W |
|---|---|---|
| Model | Raspberry Pi 4B (2GB min, 4GB recommended) | Raspberry Pi Zero 2W |
| RAM | 4GB | 512MB |
| CPU | Cortex-A72 (1.5GHz quad-core) | Cortex-A53 (1GHz quad-core) |
| OS | Raspberry Pi OS Lite 64-bit | Raspberry Pi OS Lite 64-bit |
| USB offload | USB-A stick (FR-11) | USB OTG gadget mode (FR-12) |
| Typical use | Office/home, desk-mounted | On the go, pocket-sized |

> **Note:** Pi 3B/3B+ (1GB) are not supported. Pi 5 compatibility is untested.

## Audio HAT

Earshot uses the ReSpeaker HAT (selected via `hardware.hat` in `config.toml`).

| Component | Detail |
|---|---|
| Audio codec | Built-in I2S codec |
| ALSA card name | `seeed-2mic-voicecard` |
| Microphones | 2x onboard MEMS mics |
| LED | APA102 RGB LEDs x3 (SPI-controlled) — 1 used, v1 |
| Button | GPIO17 |
| Speaker | None |

