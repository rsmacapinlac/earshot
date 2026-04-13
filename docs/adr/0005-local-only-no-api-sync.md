# 0005 — Local-Only Recorder, No API Sync

**Status:** Accepted

## Context

The original design sent audio to an API for server-side transcription and diarization. This required internet connectivity, API credentials, a background upload worker, sync state tracking, and retry logic.

The device has two target form factors with distinct offload needs: a desk-mounted Pi 4B (USB-A ports available) and a portable Pi Zero 2W (USB OTG data port). In both cases, physical USB offload covers the user's workflow — recordings are moved to a USB stick (Pi 4B) or pulled by a laptop (Pi Zero 2W).

## Decision

Earshot is a local-only audio recorder with on-device transcription. No API endpoint, no network upload, no external service dependencies. Recordings are Opus-encoded audio files offloaded physically via USB.

WiFi remains configured at the OS level for SSH access during setup and configuration, but the application has no network dependency.

## Consequences

- No external API credentials, authentication, or endpoint configuration required.
- No background upload worker, connectivity polling, or sync state.
- On-device transcription using open-source models (Whisper via faster-whisper).
- All processing and storage is local — no data leaves the device.
