# Processing

The Pi performs no transcription or diarization. Its only post-recording processing is encoding the captured WAV to MP3 (see Storage). Transcription and diarization are performed server-side by the API after the audio is uploaded (see api-sync.md).

## FR-5: Encoding Failure

- If encoding fails, the raw WAV file is retained.
- The LED fast-blinks **red** three times before returning to solid **green**.
- The failure is logged to the SQLite `events` table with the error detail.
- The recording's `processing_state` is set to `failed` in the `recordings` table.
- Failed encodings are not automatically retried (can be addressed in a future version).
