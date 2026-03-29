# 0001 — On-Device Audio Processing

**Status:** Accepted

## Context
After recording, audio must be diarized and transcribed. This could be handled on-device or by sending audio to an external cloud service (e.g. AWS Transcribe, Google Speech-to-Text).

The device is intended to operate reliably in environments without guaranteed internet connectivity.

## Decision
All audio processing (diarization and transcription) runs locally on the Raspberry Pi 4B.

## Consequences
- The device is fully functional offline with no dependency on external services.
- Constrains model selection to those that run acceptably on a Pi 4B (4GB RAM, no GPU).
- Processing time will be longer than cloud alternatives — acceptable given the use case is not real-time.
- Minimum hardware target is raised to Pi 4B 2GB to accommodate model memory requirements.
- No audio ever leaves the device during processing, which is a privacy benefit.
