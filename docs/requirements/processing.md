# Processing

The Pi's only post-recording processing is encoding each captured WAV chunk to Opus. No transcription or diarization is performed on-device or server-side.

> See [device-state.md](device-state.md) for LED behaviour during encoding states.

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
