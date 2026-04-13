# Transcription

On-device transcription is an opt-in feature that converts completed recording sessions to text using faster-whisper (CTranslate2-based inference). Transcription runs during idle time and does not compete with recording.

> See [device-state.md](device-state.md) for LED behaviour during the Transcribing state.
> See [configuration.md](configuration.md) for the `[transcription]` config section.

---

## FR-14: Transcription Queue

- Transcription is enabled by default. It is active unless `transcription.enabled = false` in `config.toml`.
- A session is **pending transcription** when its directory contains `session.wav` (the concatenated recording) but no `transcript.md`.
- The queue is implicit — derived from the filesystem at runtime. No separate queue file is maintained.
- Sessions are processed **FIFO** (oldest session directory first, by directory name timestamp).
- The queue persists across reboots. A session remains pending until `transcript.md` is successfully written.

### FR-14a: Queue Scheduling

- Transcription runs only when the device is in idle state + 3m and the transcription queue is non-empty.
- If the user begins a recording while transcription is running, transcription is cancelled immediately. The in-progress session returns to the **front** of the queue. Recording takes priority.
- On next return to idle (after encoding completes), the queue is checked and transcription resumes from the front.
- On boot, the queue is evaluated as part of the startup sequence. Any pending sessions discovered on boot are processed in FIFO order once the device reaches idle.

---

## FR-15: Transcription Process

- The `session.opus` file (created by encoding `session.wav` at the end of recording) is passed to `WhisperModel.transcribe()` with language set to English and configurable beam search width.
- faster-whisper uses ffmpeg for audio decoding, so it can read opus files directly.
- The model reads the audio file lazily during segment iteration; no decoding happens until iteration begins.
- On success: `transcript.md` is written to the session directory. The session is no longer pending.
- On failure: no `transcript.md` is written. The session remains at the front of the queue. The failure is logged to the systemd journal. Transcription is retried on the next idle window.

---

## FR-16: Transcript Format

The output file is `transcript.md` in the session directory. The format is compatible with earshot-tui transcript output.

```markdown
# Recording — YYYY-MM-DD HH:MM:SS
**Duration:** Xh Xm Xs
**Processed:** YYYY-MM-DD HH:MM:SS

---

[MM:SS] segment text
[HH:MM:SS] segment text
```

- The header timestamp is the session directory name parsed to a human-readable date.
- **Duration** is the total audio duration across all chunks, derived from the concatenated audio.
- **Processed** is the wall-clock time transcription completed.
- Each segment line uses `[MM:SS]` for timestamps under one hour, `[HH:MM:SS]` for one hour or beyond.
- Segment text is the raw transcription output from faster-whisper with no post-processing applied.

### Filesystem state with transcription enabled

| Directory contents | Meaning |
|---|---|
| `recording-NNN.wav` only | Chunk recorded, awaiting session end |
| `recording-NNN.wav` (×N) + `session.wav` | Recording completed, chunks concatenated |
| `recording-NNN.wav` + `session.wav` + `session.opus` | Recording encoded; awaiting transcription |
| `session.wav` + `session.opus` + `transcript.md` | Fully processed |
| `recording-NNN.wav` + `.failed_NNN` marker | Orphaned WAV from prior crash (recovery path) |
| `session.opus` + `transcript.md` | Transcript complete; WAV may be deleted (implementation detail) |

---

## FR-17: LED During Transcription

> Full LED table and pattern definitions are in [device-state.md](device-state.md).

- While transcription is running, the LED pulsates **amber** (slow, ~1.5–2 second cycle).
- Amber is distinct from warning **orange** (`#FF8000`) — amber uses `#FFB300` (more yellow). The slower pulsate cycle further differentiates it from orange warning states.
- When the transcription queue empties, the LED returns to solid **green** (standard idle state). No flash or transition animation.
- On the ReSpeaker HAT, the LED is the only feedback channel.

---

## FR-18: Installer Requirements

- The installer (`installer/install.sh`) installs transcription support by default.
- The installer:
  1. Installs `faster-whisper` via pip (no build step required).
  2. Pre-downloads the configured model to `~/.local/share/earshot/models/` (default: `tiny.en`, ~35 MB INT8 quantization).
  3. Writes `transcription.enabled = true` and `transcription.model` to `config.toml`.
- Users who do not want transcription can set `transcription.enabled = false` in `config.toml` after installation, or pass `--no-transcription` to the installer to skip the model download.

---

## Hardware Notes

### Pi 4B

- Recommended model: `tiny.en` (Q5_1). Transcribes a 15-minute session in approximately 3–6 minutes.
- `base.en` (Q5_1) is supported for better accuracy; transcribes a 15-minute session in approximately 7–13 minutes.
- Thread count default: 2 (leaves headroom for recording and encoding on the 4-core CPU).

### Pi Zero 2W

- Only `tiny.en` (Q5_1) is supported. RAM budget (~130 MB for model + inference) is the binding constraint; larger models exceed the available headroom.
- Transcribes a 15-minute session in approximately 7–18 minutes.
- Thread count default: 2.
- Transcription of long sessions will queue for an extended period. This is expected behaviour.
