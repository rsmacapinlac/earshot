# Open Questions

| # | Question | Impact |
|---|---|---|
| OQ-1 | What is the API schema / endpoint for audio upload? | api-sync.md |
| OQ-2 | Does the API return transcription results back to the device, or are results only accessible server-side? | api-sync.md, storage.md |
| OQ-4 | Should failed / unsynced uploads retry indefinitely or expire? | api-sync.md |
| OQ-5 | Authentication mechanism for the API (API key, OAuth, etc.)? | api-sync.md |
| TQ-2 | Where is the temporary WAV file written? If stored in `/tmp`, a reboot would delete it before recovery logic can find and encode it. | storage.md, non-functional.md |
| TQ-7 | What happens if the MP3 upload fails partway through? Partial upload state needs a defined recovery path. | api-sync.md |
| UX-1 | Should the device emit an audio cue (beep) on state transitions? Requires a speaker — out of scope for v1 but worth noting for v2. | recording.md |
| UX-3 | Should there be a visible indicator for recordings pending sync (e.g. slow blue pulsating while idle)? | recording.md, api-sync.md |
