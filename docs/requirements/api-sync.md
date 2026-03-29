# API Sync

## FR-7: API Sync
- When internet connectivity is available, upload both `audio.mp3` and `result.json` to the configured API endpoint.
- If offline, queue the result for upload when connectivity is restored.
- Each recording is only synced once (sync state tracked locally).
