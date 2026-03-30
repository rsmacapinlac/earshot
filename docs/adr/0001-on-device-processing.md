# 0001 — Audio Processing

**Status:** Accepted

## Context

After recording, audio must be diarized and transcribed. This can be handled on-device or by sending audio to an external service.

The original design required all processing to run on the Pi 4B. This imposed significant constraints: model selection was limited to what fits in 4GB RAM with no GPU, processing was slow, and the installer required downloading ~1GB of models and a Hugging Face account. The device's primary use case is recording conversations for later review — transcription does not need to happen on-device.

## Decision

Transcription and diarization will be performed server-side by the API. The Pi is responsible only for recording audio, encoding to Opus, storing recordings locally, and uploading to the API when connectivity is available.

## Consequences

- The Pi has no model memory or CPU constraints for processing.
- Install is significantly simpler: no PyTorch, no Whisper, no pyannote, no Hugging Face token required.
- `result.json` is not generated on-device — results are owned by the API.
- The "blue pulsing" phase after recording covers only the fast WAV→Opus encode step.
- The device requires internet connectivity to produce transcripts. Recordings are never lost (audio is retained locally), but transcription only happens once audio is uploaded.
- The API endpoint is required for transcription; without one configured, the device is an audio recorder only.
