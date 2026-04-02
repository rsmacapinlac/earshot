# Non-Functional Requirements

## NFR-1: No Network Dependency
The device operates entirely without internet connectivity. Recording, encoding, and USB offload all function offline. WiFi is used only for SSH access during setup and configuration.

## NFR-2: Resilience
- A crash or power loss after recording but before Opus encoding must not lose the raw audio.
- On restart, any unencoded chunks (WAV present, no Opus, no `.failed` marker) are detected and encoding is retried automatically.
- A single chunk encoding failure does not terminate the session — recording continues into the next chunk.

## NFR-3: Startup Time
Startup time targets differ by SBC due to CPU speed:

| SBC | Target |
|---|---|
| Pi 4B | 60 seconds from power-on to green-light ready |
| Pi Zero 2W | 90 seconds from power-on to green-light ready |

## Out of Scope (v1)
- Wake-word detection (always button-triggered)
- Real-time / live transcription during recording
- Multi-device coordination
- Web UI or local dashboard
- Speaker identification (who a speaker is, not just that they differ)
- On-device or server-side transcription and diarization
- Audio feedback / speaker output (hardware present on Whisplay HAT — deferred to v2)
