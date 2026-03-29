# Processing

All processing runs locally on the Pi 4B after each recording stops.

## FR-5a: Speaker Diarization
- Detect and segment speakers dynamically (no fixed speaker count assumed).
- Assign a speaker label (e.g. `Speaker 1`, `Speaker 2`) to each audio segment.
- Output: timestamped speaker segments (start time, end time, speaker label).

## FR-5b: Transcription
- Transcribe each speaker segment to text using Whisper (`base` multilingual model).
- Associate each transcript with its speaker label and timestamps.
- Output: structured transcript (speaker + text + time range per turn).

## FR-5c: Processing Failure
- If processing fails at any stage, all files (`audio.mp3`, `result.json` if partially written) are always retained.
- The LED fast-blinks **red** three times before returning to solid **green**.
- The failure is logged to the SQLite `events` table with the error detail.
- The recording's `processing_state` is set to `failed` in the `recordings` table.
- Failed recordings are not automatically retried (can be addressed in a future version).
