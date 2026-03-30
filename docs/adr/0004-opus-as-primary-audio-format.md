# 0004 — Opus as Primary Audio Storage Format

**Status:** Accepted

## Context

Audio is captured as a WAV file (uncompressed). WAV files are large (~10MB/min at 16kHz mono) and storage on a Pi SD card is limited. The encoded file is uploaded to an API for server-side transcription and diarization.

Options considered:

| Format | Bitrate for equivalent speech quality | Notes |
|---|---|---|
| WAV | — (uncompressed) | Maximum quality, impractical for storage/upload |
| MP3 | ~128 kbps | Widely compatible; not optimised for speech at low bitrates |
| Opus | ~32 kbps | Purpose-built for speech; far better compression at low bitrates |

## Decision

Encode the WAV to Opus immediately after recording, then delete the WAV. Opus is the primary and only persisted audio format (`.opus` container, `libopus` codec via ffmpeg).

### Pipeline
1. Capture audio to a temporary WAV file.
2. Encode WAV to Opus via `ffmpeg` (default 32 kbps, configurable).
3. Confirm `.opus` file is written successfully.
4. Delete the temporary WAV.
5. Queue the `.opus` file for API upload.

## Consequences

- ~4x smaller files than equivalent-quality MP3 — reduces SD card usage and upload time.
- Opus natively handles 16kHz mono speech without resampling.
- ffmpeg must be installed as a system dependency (unchanged from MP3).
- Lossy compression means the original uncompressed audio is not retained. Acceptable given storage constraints.
- The API endpoint must accept Opus audio. This is a dependency on the API design (see OQ-1 in open-questions.md).
- The WAV is a temporary file only; a crash between capture and encoding leaves the WAV on disk. Resilience logic should detect and re-encode unprocessed WAVs on restart.
