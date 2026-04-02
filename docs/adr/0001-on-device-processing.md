# 0001 — On-Device Audio Processing

**Status:** Superseded by ADR-0010

## Context

The original design required all transcription and diarization to run locally on the Pi 4B using Whisper (ADR-0003) and pyannote.audio (ADR-0002). This imposed significant constraints: model selection was limited to what fits in 4GB RAM with no GPU, processing was slow (several minutes per hour of audio on Pi 4B hardware), and the installer required downloading ~1GB of models and a Hugging Face account.

## Decision

Keep all processing on-device: record, diarize, and transcribe locally without any external service.

## Consequences

- No API credentials or network dependency for transcription.
- Significant installer complexity: PyTorch, Whisper, pyannote, Hugging Face token, model download.
- Processing time is a constraint — the device is unavailable for recording while processing.
- Superseded by ADR-0010, which removed transcription and diarization entirely from scope. The Pi now records and encodes only; post-processing is the user's responsibility after USB offload.
