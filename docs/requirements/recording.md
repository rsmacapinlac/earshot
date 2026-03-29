# Recording

## LED States

| State | Colour | Pattern |
|---|---|---|
| Booting | White | Slow pulsating |
| Ready / idle | Green | Solid |
| Recording | Red | Slow pulsating |
| Processing | Blue | Slow pulsating |
| Sync complete | Blue | Single flash |
| Processing failure | Red | Fast blink (×3) then returns to green |
| Disk threshold reached | Orange | Slow pulsating |
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
- Maximum recording duration is 1 hour (configurable). When the limit is reached, recording stops automatically as if the button had been pressed.
- Pressing the button while idle begins audio recording, provided the disk threshold has not been reached.
- If the disk threshold has been reached, the button is ignored and the LED remains pulsating **orange**.
- The LED pulsates **red** (slow) during recording.
- A minimum recording duration of 3 seconds is enforced (configurable). If the button is pressed before the minimum is reached, the recording is discarded and the LED double-flashes **green** to signal the device is ready.
- Audio is captured at the following spec:

| Parameter | Value |
|---|---|
| Sample rate | 16kHz |
| Bit depth | 16-bit PCM |
| Channels | Stereo (both mics captured) |

> **Note:** 16kHz is the ReSpeaker HAT's native sample rate and the expected input rate for both Whisper and pyannote.audio. The stereo capture is downmixed to mono before processing.

## FR-3: Stop Recording
- Pressing the button again stops the recording (subject to minimum duration).
- The raw audio is saved locally immediately (before processing begins).
- The LED pulsates **blue** (slow) while diarization and transcription run.
- The LED returns to solid **green** once processing is complete.
- If processing fails, the LED fast-blinks **red** three times before returning to solid **green**.
- Button presses are ignored during processing — new recordings are blocked until the device returns to idle.

## FR-4: Safe Shutdown
- Holding the button for 3 seconds while idle initiates a safe shutdown (duration configurable).
- The LED transitions from green to slow pulsating **white**.
- The LED fades to off when it is safe to unplug the device.
- Button hold during recording or processing is ignored.
