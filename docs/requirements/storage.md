# Storage

## FR-6: Local Storage
- Raw audio is always saved locally until successfully uploaded.
- Default storage path: `~/earshot/recordings/<YYYYMMDDTHHMMSS>/` (e.g. `20260329T143022`)
- The recordings directory is configurable via `storage.recordings_dir` in `config.toml` (e.g. to point at a USB drive).
  - `audio.opus` — compressed recording (encoded via `ffmpeg`, mono, 16kHz, default 32 kbps, configurable)

### Disk Space Management
- Disk space is checked before each new recording begins.
- If the configurable threshold is reached, the LED pulsates **orange** and new recordings are blocked.
- The device recovers automatically once files are manually removed and disk space drops below the threshold.
- Threshold is configurable (default: 90% disk usage) to avoid completely filling the SD card.

### Recording Pipeline
1. Capture audio to a temporary WAV file.
2. Encode WAV to Opus.
3. Delete the WAV once the `.opus` file is confirmed written.
4. Queue the recording for API upload.
