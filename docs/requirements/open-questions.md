# Open Questions

| # | Question | Impact |
|---|---|---|
| OQ-1 | What is the API schema / endpoint for result upload? | api-sync.md |
| OQ-4 | Should failed / unsynced uploads retry indefinitely or expire? | api-sync.md |
| OQ-5 | Authentication mechanism for the API (API key, OAuth, etc.)? | api-sync.md |
| TQ-2 | Where is the temporary WAV file written? If stored in `/tmp`, a reboot would delete it before recovery logic can find and process it. | storage.md, non-functional.md |
| TQ-3 | What is the `result.json` schema? Speaker labels, timestamps, transcript text — needs a defined structure before API or storage work begins. | storage.md, api-sync.md |
| TQ-7 | What happens if the MP3 uploads successfully but `result.json` does not (or vice versa)? Partial upload state needs a defined recovery path. | api-sync.md |
| UX-1 | Should the device emit an audio cue (beep) on state transitions? Requires a speaker — out of scope for v1 but worth noting for v2. | recording.md |
| UX-3 | Should there be a visible indicator for recordings pending sync (e.g. slow blue pulsating while idle)? | recording.md, api-sync.md |
