# 0004 — MP3 as Primary Audio Storage Format

**Status:** Accepted

## Context
Audio is captured as a WAV file (uncompressed). WAV files are large (~10MB/min at 44.1kHz stereo) and storage on a Pi SD card is limited.

Options considered:
- Retain WAV as the primary format
- Encode to a compressed format and delete the WAV
- Retain both

## Decision
Encode the WAV to MP3 immediately after recording, then delete the WAV. MP3 is the primary and only persisted audio format.

### Pipeline
1. Capture audio to a temporary WAV file.
2. Encode WAV to MP3 via `ffmpeg` (default 128 kbps, configurable).
3. Confirm MP3 is written successfully.
4. Delete the temporary WAV.
5. All subsequent processing (diarization, transcription) operates on the MP3.

## Consequences
- Significantly reduces storage usage (~10x smaller than WAV at 128 kbps).
- Both Whisper and pyannote.audio accept MP3 input natively — no processing penalty.
- The WAV is a temporary file only; a crash between capture and encoding would result in the WAV being left on disk. Resilience logic should detect and recover unprocessed WAVs on restart.
- ffmpeg must be installed as a system dependency.
- Lossy compression means the original uncompressed audio is not retained. Acceptable given storage constraints.
