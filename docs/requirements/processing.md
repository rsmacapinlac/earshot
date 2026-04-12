# Processing

Post-recording processing has two stages: concatenation & encoding (always on) and transcription (opt-in).

1. All captured WAV chunks are concatenated into a single `session.wav`.
2. The `session.wav` is encoded to `session.opus` (stereo, 16kHz, default 32 kbps, configurable).
3. Once the `session.opus` is confirmed written, the session is queued for transcription if `transcription.enabled = true`.

No diarization is performed on-device.

> See [device-state.md](device-state.md) for LED behaviour during transcription states (encoding is not user-visible).
> See [transcription.md](transcription.md) for transcription queue, format, and hardware requirements.

## FR-6: Recording and Encoding

- Audio is recorded in configurable chunks (default: 15 minutes) as WAV files (`recording-001.wav`, `recording-002.wav`, etc.).
- WAV chunks are retained in memory on the device during recording — no background encoding occurs.
- When the user presses the button to end the recording:
  1. All `recording-*.wav` chunks are concatenated into `session.wav` via `ffmpeg` (no re-encoding, copy mux).
  2. The `session.wav` is encoded to `session.opus` via `ffmpeg` (stereo, 16kHz, configurable bitrate).
  3. Both `session.wav` and `session.opus` persist in the session directory.
  4. Recording WAV chunks (`recording-*.wav`) also persist for crash recovery (NFR-2).

## FR-6a: Encoding Failure

- If concatenation or encoding fails, an error is logged to the systemd journal.
- The `session.wav` and individual `recording-*.wav` files are retained for manual recovery or retry on next boot.
- The session may still be queued for transcription if a partial `session.opus` was written.
- The LED does not provide user feedback for encoding failures in this phase (encoding is not user-visible).
