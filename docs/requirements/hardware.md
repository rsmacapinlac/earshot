# Hardware

## Single Board Computer

Earshot targets two distinct use cases with different hardware:

| | Desk (Pi 4B) | Portable (Pi Zero 2W) |
|---|---|---|
| Model | Raspberry Pi 4B 4GB | Raspberry Pi Zero 2W |
| RAM | 4GB | 512MB |
| CPU | Cortex-A72 (1.5GHz quad-core) | Cortex-A53 (1GHz quad-core) |
| OS | Raspberry Pi OS Lite 64-bit | Raspberry Pi OS Lite 64-bit |
| Offload | USB-A stick (FR-11) | USB OTG gadget mode (FR-12) |
| Use case | Office/home, desk-mounted | On the go, pocket-sized |

> **Note:** Pi 3B/3B+ (1GB) are not supported. Pi 5 compatibility is untested.

## Power

| Model | Battery Module |
|---|---|
| Pi 4B | PiSugar 2 Plus (5000 mAh) |
| Pi Zero 2W | PiSugar S for Zero (or equivalent) |

- The PiSugar connects via pogo pins on the underside of the Pi (I2C + direct GPIO 5V power delivery).
- No USB ports are occupied by the battery module.
- **Pi 4B:** USB-C port is left free for USB gadget (file offload) use — see FR-11.
- **Pi Zero 2W:** Dedicated micro-USB power port is used for the PiSugar; the OTG micro-USB port is free for USB gadget use — see FR-11.

## Audio HAT

| Component | Detail |
|---|---|
| Audio HAT | Seeed ReSpeaker 2-Mic Pi HAT |
| Microphones | 2x onboard MEMS mics |
| LED | APA102 RGB LEDs x3 (onboard HAT, controlled via SPI) — 1 used, v1 |
| Button | User button on GPIO17 (onboard HAT) |
