# 0006 — Filesystem as State, No SQLite

**Status:** Accepted

## Context

SQLite was previously chosen to track recording lifecycle state and API upload state. With API sync removed (ADR-0005), the upload tracking purpose disappears entirely. The remaining state — whether a chunk has been encoded, whether encoding failed — can be represented directly by the filesystem.

## Decision

Use the filesystem as the sole state store. No SQLite database.

State is derived from the presence and combination of files in each session directory:

| Contents | Meaning |
|---|---|
| `audio_NNN.wav` only | Recording or interrupted before encode |
| `audio_NNN.wav` + `audio_NNN.opus` | Encode in progress |
| `audio_NNN.opus` only | Successfully encoded |
| `audio_NNN.wav` + `.failed_NNN` | Encoding failed; WAV retained |

Application errors are logged to the systemd journal (already present via ADR-0004).

## Consequences

- No SQLite dependency, no schema migrations, no database file to manage.
- Recovery on boot is a filesystem scan rather than a database query — equally simple at this scale.
- No cross-recording query capability (was only used for upload tracking, which is now gone).
