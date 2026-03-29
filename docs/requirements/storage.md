# Storage

## FR-6: Local Storage
- Raw audio and structured results are always saved locally.
- Storage path: `~/earshot/recordings/<YYYYMMDDTHHMMSS>/` (e.g. `20260329T143022`)
  - `audio.mp3` — compressed recording (encoded via `ffmpeg`, mono, 16kHz, default 128 kbps, configurable)
  - `result.json` — diarization + transcript output

### Disk Space Management
- Disk space is checked before each new recording begins.
- If the configurable threshold is reached, the LED pulsates **orange** and new recordings are blocked.
- The device recovers automatically once files are manually removed and disk space drops below the threshold.
- Threshold is configurable (default: 90% disk usage) to avoid completely filling the SD card.

### Recording Pipeline
1. Capture audio to a temporary WAV file.
2. Encode WAV to MP3.
3. Delete the WAV once MP3 is confirmed written.
4. All subsequent processing (diarization, transcription) operates on the MP3.
