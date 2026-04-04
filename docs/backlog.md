# Backlog

Items that are out of scope for the current release but are candidates for future work. Grouped by theme, roughly ordered by likely priority within each group.

---

## Audio Feedback (v2)

Speaker output is available on the Whisplay HAT but not implemented in v1.

| ID | Item | Notes |
|---|---|---|
| B-A1 | Audio cues on state transitions | Short tones on start recording, stop recording, USB transfer complete, error. Requires `AudioOutputInterface` implementation in `earshot/hal/whisplay.py`. Config key `[audio]` is stubbed in `config.toml`. |
| B-A2 | Configurable audio feedback volume | Via `[audio]` section in `config.toml` |

---

## Transcription

| ID | Item | Notes |
|---|---|---|
| B-T1 | `storage.require_transcript_before_offload` | Config option to block USB offload until all pending transcription is complete. Useful for users who always want transcripts on the stick. Deferred because offload-regardless is the safer default. |
| B-T2 | `base.en` model as installer option | Currently only `tiny.en` (Q5_1) is the default. `base.en` (Q5_1, 57 MB) offers better accuracy on Pi 4B. Installer could offer a model choice prompt. |
| B-T3 | Transcription retry limit | After N consecutive failures on a session, mark it with a `.failed_transcription` marker and move on rather than retrying indefinitely. |
| B-T4 | Real-time / live transcription | Transcribe audio as it is recorded, not post-session. Significant complexity; out of scope until post-session transcription is stable. |

---

## Speaker Diarization

| ID | Item | Notes |
|---|---|---|
| B-D1 | On-device speaker diarization | Identify distinct speakers in the transcript (Speaker 1, Speaker 2, …). Not speaker identification — just that speakers differ. Requires a diarization model (e.g. pyannote) that fits within hardware constraints. RAM budget on Pi Zero 2W makes this impractical; Pi 4B only. |

---

## Recording

| ID | Item | Notes |
|---|---|---|
| B-R1 | Wake-word detection | Start recording automatically on a trigger word rather than a button press. Always button-triggered in v1. |
| B-R2 | Multi-device coordination | Multiple Earshot devices recording the same session, synced timestamps. No design work done. |

---

## Infrastructure / UX

| ID | Item | Notes |
|---|---|---|
| B-I1 | Web UI / local dashboard | Browser-accessible interface over WiFi for reviewing recordings and transcripts without USB offload. Docker would be a natural fit for the companion server component (see ADR-0002). |
| B-I2 | Pi 5 support | Pi 5 (Cortex-A76, 2.4 GHz) is approximately 3–5× faster than Pi 4B for transcription. Compatibility is untested; likely straightforward but needs verification. |
| B-I3 | WiFi onboarding without SSH | Add a hotspot or captive portal for configuring WiFi without needing an existing network connection. |
