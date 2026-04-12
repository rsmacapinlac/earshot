# Device State

## LED States

| State | Colour | Pattern |
|---|---|---|
| Booting | White | Slow pulsating |
| Ready / idle | Green | Solid |
| Recording | Red | Slow pulsating |
| Post-recording (encoding) | Amber | Slow pulsating |
| USB transfer | Blue | Slow pulsating |
| USB transfer complete | Blue | Single flash |
| USB transfer error | Orange | Slow pulsating |
| Disk threshold reached | Orange | Slow pulsating |
| Transcribing | Amber | Slow pulsating (~1.5–2s cycle) |
| Shutting down | White | Slow pulsating → fade to off |

### Pattern Definitions

| Pattern | Description |
|---|---|
| Solid | Constant on |
| Slow pulsating | Smooth fade in/out, ~1 second cycle |
| Fast blink | Sharp on/off, ~0.2 second cycle |
| Fade to off | Slow brightness decrease to off |

---

## FR-1: Idle State
- On startup, the LED pulsates **white** during boot.
- Once ready, the LED transitions to solid **green**.
- If the disk threshold is reached on startup, the LED pulsates **orange** instead and the device waits for files to be removed.
- The application waits for a button press.

## FR-2: Start Recording
- Pressing the button while idle begins a recording session, provided the disk threshold has not been reached.
- If transcription is running when the button is pressed, transcription is cancelled immediately and the in-progress session is returned to the front of the transcription queue. Recording begins without delay.
- If the disk threshold has been reached, the button is ignored and the LED remains pulsating **orange**.
- The LED pulsates **red** (slow) during recording.
- A minimum recording duration of 3 seconds is enforced (configurable). If the button is pressed before the minimum is reached, the recording is discarded and the LED double-flashes **green** to signal the device is ready.
- Audio is captured at the following spec:

| Parameter | Value |
|---|---|
| Sample rate | 16kHz |
| Bit depth | 16-bit PCM |
| Channels | Stereo (both mics captured) |

> **Note:** 16kHz is the target sample rate for both supported HATs. The stereo capture is downmixed to mono before encoding.

### FR-2a: Chunked Recording
- Within a session, audio is recorded in configurable chunks (default: 15 minutes).
- When the chunk duration is reached, the current chunk is closed and a new chunk file begins automatically without interrupting the session.
- Completed chunks are retained as WAV files on the device; no background encoding occurs during recording.
- Chunk duration is configurable via `recording.chunk_duration_seconds` in `config.toml`.
- There is no maximum session duration — recording continues until the button is pressed or the disk threshold is reached.
- **If the disk threshold is reached mid-session:** recording stops immediately, the current chunk WAV is closed. Concatenation and encoding are attempted after recording stops. If encoding fails due to insufficient disk space, the WAV files are retained for manual recovery or retry on next boot.

## FR-3: Stop Recording
- Pressing the button again stops the session (subject to minimum duration).
- Recording completes immediately; all WAV chunks are concatenated into `session.wav` and encoded to `session.opus` without user-visible delay.
- The LED transitions from red pulsate directly to green solid once recording ends and encoding completes.
- If concatenation or encoding fails, an error is logged but the session persists. The LED returns to green; transcription may still proceed if a partial `session.opus` was written.
- Button presses are ignored during recording or if an error is being logged — new recordings are blocked until the device returns to idle.

## FR-4: Safe Shutdown
- Holding the button for 3 seconds while idle initiates a safe shutdown (duration configurable).
- The LED transitions from green to slow pulsating **white**.
- The LED fades to off when it is safe to unplug the device.
- Button hold during recording or processing is ignored.

## FR-5: Audio Feedback *(deferred to v2)*

Speaker output is available on the Whisplay HAT. Audio cues on state transitions are planned for v2. No `AudioOutputInterface` implementation is required for v1.

> See [display.md](display.md) for corresponding LCD display behaviour on the Whisplay HAT.
