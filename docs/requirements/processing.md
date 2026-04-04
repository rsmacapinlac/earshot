# Processing

Post-recording processing has two stages: encoding (always on) and transcription (opt-in).

1. Each captured WAV chunk is encoded to Opus.
2. Once all chunks in a session are encoded, the session is queued for transcription if `transcription.enabled = true`.

No diarization is performed on-device.

> See [device-state.md](device-state.md) for LED behaviour during encoding and transcription states.
> See [transcription.md](transcription.md) for transcription queue, format, and hardware requirements.

## FR-6: Encoding

- Each chunk WAV is encoded to Opus via `ffmpeg` (mono, 16kHz, default 32 kbps, configurable).
- Encoding runs in the background as each chunk completes, pipelined with ongoing recording.
- On success, the WAV is deleted once the `.opus` file is confirmed written.

## FR-6a: Encoding Failure

- If encoding fails, the raw WAV is retained alongside a `.failed_NNN` marker file.
- The LED fast-blinks **red** three times before returning to its previous state.
- The failure is logged to the systemd journal.
- The recording session continues — subsequent chunks are not affected by a single chunk's failure.
- Failed chunks are retried automatically on next boot.
