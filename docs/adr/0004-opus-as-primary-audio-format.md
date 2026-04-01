# 0004 — Opus as Primary Audio Storage Format

**Status:** Accepted

## Context

Audio is captured as a WAV file (uncompressed). WAV files are large (~10MB/min at 16kHz mono) and storage on a Pi SD card is limited. Compression reduces on-device storage pressure and results in smaller files on the offload USB stick.

Options considered:

| Format | Bitrate for equivalent speech quality | Notes |
|---|---|---|
| WAV | — (uncompressed) | Maximum quality, impractical for storage |
| MP3 | ~128 kbps | Widely compatible; not optimised for speech at low bitrates |
| Opus | ~32 kbps | Purpose-built for speech; far better compression at low bitrates |

## Decision

Encode the WAV to Opus immediately after recording, then delete the WAV. Opus is the primary and only persisted audio format (`.opus` container, `libopus` codec via ffmpeg).

### Pipeline
1. Capture audio to a temporary WAV file.
2. Encode WAV to Opus via `ffmpeg` (default 32 kbps, configurable).
3. Confirm `.opus` file is written successfully.
4. Delete the temporary WAV.
5. The `.opus` file is retained on-device until offloaded via USB.

## Consequences

- ~4x smaller files than equivalent-quality MP3 — reduces SD card usage and USB stick footprint.
- Opus natively handles 16kHz mono speech without resampling.
- ffmpeg must be installed as a system dependency (unchanged from MP3).
- Lossy compression means the original uncompressed audio is not retained. Acceptable given storage constraints.
- The WAV is a temporary file only; a crash between capture and encoding leaves the WAV on disk. Resilience logic detects and re-encodes unprocessed WAVs on restart (see ADR-0011).
