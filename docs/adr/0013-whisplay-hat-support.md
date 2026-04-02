# 0013 — Whisplay HAT as a Supported Audio HAT

**Status:** Accepted

## Context

The initial design targeted a single hardware configuration: Pi 4B with the Seeed ReSpeaker 2-Mic Pi HAT. This covers the desk/office use case well but is not practical for portable use — the Pi 4B is large, and the ReSpeaker HAT is designed for the 40-pin header of full-size Pi boards.

For the portable form factor (Pi Zero 2W), a more compact, integrated HAT is needed. The Whisplay HAT (PiSugar) was identified as a strong fit:

- Matches the Pi Zero 2W form factor (65×30mm)
- Provides dual MEMS microphones, a speaker, discrete RGB LEDs, and a button — all required peripherals in a single board
- Adds a 1.69" LCD display not present on the ReSpeaker
- Compatible with the Pi 4B GPIO header as well, enabling any SBC/HAT combination

The key complication is that both HATs use the WM8960 audio codec, but with **different, mutually exclusive drivers**: seeed-voicecard ships a patched WM8960 kernel module that replaces the upstream module, which the Whisplay HAT requires. The installer cannot install both; it must be HAT-aware.

## Decision

Add the Whisplay HAT as a second supported HAT alongside the ReSpeaker. The HAT choice is independent of the SBC choice — any supported HAT can be paired with any supported SBC. The active HAT is configured via `hardware.hat` in `config.toml` and selected at both install time (driver selection) and runtime (HAL implementation selection).

## Consequences

- The installer must be HAT-aware: it reads `hardware.hat` and installs only the appropriate audio driver. Switching HATs requires re-running the installer.
- The HAL (ADR-0007) gains two new interface implementations per HAT: `AudioOutputInterface` (speaker) and `DisplayInterface` (LCD) — both no-ops on the ReSpeaker.
- New capabilities are available on Whisplay: speaker for audio feedback (FR-5), LCD for display (FR-13).
- The ReSpeaker remains fully supported — all features that rely only on LEDs and audio capture work identically on both HATs.
- A new config document (`configuration.md`) was introduced to centralise all config key definitions.
