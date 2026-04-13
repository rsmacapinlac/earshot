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
- Speaker identification / diarization (who is speaking) — *see Constraints below*
- Server-side transcription
- Audio feedback / speaker output (deferred to v2)

## Constraints

### Diarization Not Feasible on Pi

Speaker diarization (identifying which speaker is currently speaking) cannot be implemented on-device due to ARM64 hardware limitations:

**Root cause:** The diarization pipeline (pyannote.audio + speaker embedding models) requires CUDA-capable GPU acceleration or extremely long inference times (~5+ minutes for a 15-minute session). Raspberry Pi has no CUDA support and lacks the CPU performance to run diarization inference in reasonable time.

**Technical details:**
- pyannote.audio uses PyTorch models that require `torchcodec` for audio loading
- torchcodec requires CUDA to build; no pre-built ARM64 wheels exist
- Alternative approaches (FFmpeg subprocess for audio loading) succeeded in loading audio but diarization inference remained impractical: >5 minute timeout on ARM64, no speakers detected
- The speech embedding and clustering models are designed for GPU computation; CPU-only inference on ARM is orders of magnitude slower

**Recommendation:** If speaker identification is needed, offload recordings and process with desktop tools (e.g., pyannote on a laptop with GPU) as part of post-processing workflow. This is consistent with Earshot's philosophy: on-device recording only; processing deferred to USB offload + companion tools.
