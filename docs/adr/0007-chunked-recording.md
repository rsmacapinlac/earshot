# 0007 — Chunked Recording (15-Minute Default)

**Status:** Accepted

## Context

A single session could run for hours. Writing audio continuously to a single file means a crash or power loss mid-session loses everything recorded since the last stop. Additionally, encoding the entire session after the button is pressed introduces a long delay before the device is ready again.

## Decision

Within a session, audio is split into configurable chunks (default: 15 minutes). Each chunk is a separate WAV file that is encoded to Opus as soon as it closes, in parallel with the next chunk being recorded (pipeline encoding).

Chunk duration is configurable via `recording.chunk_duration_seconds` in `config.toml`. Chunks are triggered by a timer only — the button stop closes the current chunk and ends the session.

## Consequences

- Maximum data loss from a crash is one chunk duration (default: 15 minutes), not the entire session.
- Encoding is pipelined — stopping a session only requires encoding the final (partial) chunk, so the device returns to idle quickly.
- Sessions produce multiple files (`audio_001.opus`, `audio_002.opus`, …) under a single timestamped directory.
- No hard maximum session duration is needed — the device records until the button is pressed or the disk threshold is reached.
- USB stick offload moves complete session directories, so chunking is transparent to the offload path.
