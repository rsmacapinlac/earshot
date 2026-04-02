# Earshot — Requirements Index

Earshot is a Raspberry Pi application (Pi 4B or Pi Zero 2W) that records audio via a supported HAT and stores recordings locally. Recordings are offloaded physically via USB — no network connectivity is required for application functionality.

## Documents

| File | Description |
|---|---|
| [hardware.md](hardware.md) | Target hardware and components |
| [configuration.md](configuration.md) | `config.toml` schema, all keys and defaults |
| [display.md](display.md) | LCD display UX for the Whisplay HAT |
| [device-state.md](device-state.md) | Device state machine, LED and button behaviour, start/stop recording, audio feedback |
| [processing.md](processing.md) | On-device audio encoding |
| [storage.md](storage.md) | Local file storage, filesystem state, and USB offload |
| [connectivity.md](connectivity.md) | WiFi setup for SSH access |
| [install.md](install.md) | One-line installer requirements |
| [non-functional.md](non-functional.md) | Performance, resilience, and constraints |
| [open-questions.md](open-questions.md) | Unresolved decisions and open questions |
