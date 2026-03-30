# API Sync

## FR-7: API Sync

- When internet connectivity is available, upload `audio.opus` to the configured API endpoint.
- If offline, queue the recording for upload when connectivity is restored.
- Each recording is only synced once (sync state tracked locally in SQLite).
- The API is responsible for transcription and diarization after receiving the audio.
