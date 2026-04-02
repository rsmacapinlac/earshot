# Hardware

## Single Board Computers

Earshot supports two SBCs. The HAT choice is independent of the SBC choice — any supported HAT can be paired with any supported SBC.

| | Pi 4B | Pi Zero 2W |
|---|---|---|
| Model | Raspberry Pi 4B (2GB min, 4GB recommended) | Raspberry Pi Zero 2W |
| RAM | 4GB | 512MB |
| CPU | Cortex-A72 (1.5GHz quad-core) | Cortex-A53 (1GHz quad-core) |
| OS | Raspberry Pi OS Lite 64-bit | Raspberry Pi OS Lite 64-bit |
| USB offload | USB-A stick (FR-11) | USB OTG gadget mode (FR-12) |
| Typical use | Office/home, desk-mounted | On the go, pocket-sized |

> **Note:** Pi 3B/3B+ (1GB) are not supported. Pi 5 compatibility is untested.

## Audio HATs

Earshot supports two HATs. The active HAT is selected via `hardware.hat` in `config.toml`.

### Seeed ReSpeaker 2-Mic Pi HAT

| Component | Detail |
|---|---|
| Audio codec | Built-in I2S codec |
| ALSA card name | `seeed-2mic-voicecard` |
| Microphones | 2x onboard MEMS mics |
| LED | APA102 RGB LEDs x3 (SPI-controlled) — 1 used, v1 |
| Button | GPIO17 |
| Speaker | None |

### Whisplay HAT (PiSugar)

| Component | Detail |
|---|---|
| Audio codec | WM8960 (I2C control + I2S data) |
| ALSA card name | `wm8960soundcard` |
| Microphones | 2x onboard MEMS mics |
| LEDs | 3x discrete RGB LEDs — GPIO25, GPIO24, GPIO23 |
| Button | GPIO17 |
| Speaker | 8Ω 1W onboard (+ PH2.0 external mono connector, switchable) |
| Display | 1.69" LCD, 240×280px, ST7789P3 driver, SPI |

> **Note:** The Whisplay HAT's form factor matches the Pi Zero, but it is electrically compatible with the Pi 4B GPIO header as well.

