# Earshot — Requirements Index

Earshot is a Raspberry Pi application (Pi 4B or Pi Zero 2W) that records audio via a supported HAT and stores recordings locally. Recordings are offloaded physically via USB — no network connectivity is required for application functionality.

## Documents

### Hardware
| File | Description |
|---|---|
| [hardware.md](hardware.md) | Supported SBCs and HATs — specs and capabilities |

### Behaviour
| File | Description |
|---|---|
| [device-state.md](device-state.md) | Device state machine — LED colours, button behaviour, start/stop recording |

### Audio Pipeline
| File | Description |
|---|---|
| [processing.md](processing.md) | Encoding and transcription overview |
| [transcription.md](transcription.md) | On-device transcription — queue, format, and installer requirements |
| [storage.md](storage.md) | Local file storage, filesystem state, and USB offload |

### Setup & Configuration
| File | Description |
|---|---|
| [configuration.md](configuration.md) | `config.toml` schema — all keys and defaults |
| [install.md](install.md) | One-line installer requirements |
| [connectivity.md](connectivity.md) | WiFi setup for SSH access |

### Constraints & Planning
| File | Description |
|---|---|
| [non-functional.md](non-functional.md) | Performance, resilience, and out-of-scope items |
| [open-questions.md](open-questions.md) | Unresolved questions |
