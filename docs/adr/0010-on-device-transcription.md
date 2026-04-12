# 0010 — On-Device Transcription

**Status:** Accepted

## Context

ADR-0005 made Earshot a local-only recorder with no post-processing. At that point, on-device transcription was removed from scope entirely. Users who want transcripts offload recordings via USB and use desktop tools such as earshot-tui.

On-device transcription is being re-introduced as an opt-in feature for users who want transcripts on the device itself — either because they have no desktop tool, or because they want the transcript available immediately on the USB stick alongside the audio.

Two hardware targets impose meaningfully different constraints:

- **Pi 4B** (Cortex-A72, 4 cores @ 1.8 GHz, 2–4 GB RAM): capable of transcribing a 15-minute session in 3–13 minutes depending on model, with headroom for background operation.
- **Pi Zero 2W** (Cortex-A53, 4 cores @ 1 GHz, 512 MB RAM): 512 MB total; OS + Earshot + model must fit within this budget; inference is 3–5× slower than Pi 4B.

The `openai/whisper` Python package is not viable on either device: it requires ~500 MB RAM for the base model before Python framework overhead, and its inference speed is 3–5× slower than optimised ports. The Pi Zero 2W cannot run it at all.

## Decision

### 1. Engine: faster-whisper with CTranslate2

faster-whisper is a Python library wrapping OpenAI Whisper via CTranslate2, providing efficient ARM64 inference with optimized quantized models. It is imported directly into the Python application with no subprocess or binary dependency.

Key reasons over alternatives:

- **Efficient quantization support.** CTranslate2 provides INT8 and INT16 quantized models that outperform unquantized models on ARM CPUs. The tiny.en INT8 model is ~35 MB on disk and ~110 MB at runtime, fitting within the Pi Zero 2W's 512 MB budget with headroom for recording.
- **No build step required.** Unlike whisper.cpp (which requires cmake compilation or pre-built binary procurement), faster-whisper is installed via pip. The Python package includes optimized ARM64 binaries for CTranslate2.
- **Integrated VAD and lazy segment evaluation.** Built-in voice activity detection reduces transcription of silence. Segment iteration is lazy — the model reads the audio file during iteration, enabling memory-efficient pipeline designs where the session WAV file is discarded immediately after transcription completes.
- **Native Python integration.** No subprocess overhead; the model is loaded once per transcription queue and reused across sessions, eliminating startup latency.

**whisper.cpp** (original choice in ADR-0010): offers lower RAM usage via GGML quantization, but requires cmake build infrastructure on the Pi or procurement of pre-built aarch64 binaries. As of v0.2.2, faster-whisper's quantized models achieve comparable memory footprint with cleaner installation and integration.

**Vosk**: lower accuracy (~15–20% WER vs Whisper's ~5–8% on clean English). Retained as a documented fallback if faster-whisper proves unworkable on a specific hardware configuration.

**openai/whisper (PyTorch)**: 3–5× slower than faster-whisper on ARM, ~500 MB RAM minimum before framework overhead. Ruled out on both devices.

### 2. Session-level transcription, not chunk-level

Transcription operates on the full session, not on individual chunks. Recording preserves all `recording-*.wav` chunks; at the end of recording, these chunks are concatenated into a single `session.wav`, then encoded to `session.opus` via ffmpeg. Transcription reads the `session.wav` via `WhisperModel.transcribe()`.

Chunk-level transcription was rejected because:

- Whisper processes audio in 30-second windows internally. When transcribing separate chunk files, the model loses context at every 15-minute boundary — words and sentences split across chunks are transcribed without continuity.
- Session-level transcription produces a single `transcript.md` with continuous timestamps, which matches the earshot-tui output format and is more useful to the reader.
- Per-chunk `.txt` files require assembling a final transcript, complicating the state model.

**Recording pipeline change (v0.2.2)**: Previously, individual chunk WAVs were encoded to opus in the background during recording. Now, all WAV chunks are preserved and concatenated at the end of recording into `session.wav`, then transcoded to `session.opus` in a single post-recording step. This simplifies the state model and allows lazy-evaluation transcription (reading the audio file only during segment iteration, enabling immediate WAV cleanup after transcription completes).

### 3. Idle-only, FIFO queue scheduling

Transcription runs only during idle state. Sessions are queued implicitly using the filesystem (consistent with ADR-0006): a session directory containing `.opus` files but no `transcript.md` is pending transcription.

- The queue is processed FIFO (oldest session first).
- If recording begins while transcription is running, transcription is cancelled and the in-progress session returns to the front of the queue.
- The queue persists across reboots — no explicit queue file is maintained.

Concurrent background transcription (running transcription alongside recording) was considered and rejected:

- On the Pi 4B, running transcription at full thread count saturates all four cores, creating thermal and audio capture reliability risks.
- On the Pi Zero 2W, inference is slow enough that a 15-minute chunk would still be transcribing when the next chunk completes — the queue would grow indefinitely during a session.

Idle-only scheduling is consistent across both hardware targets. The Pi Zero 2W may accumulate a long queue after a recording-heavy session; this is accepted behaviour.

### 4. Output format: earshot-tui compatible transcript.md

The output file is `transcript.md` in the session directory, using the same format as earshot-tui's transcript output:

```
# Recording — YYYY-MM-DD HH:MM:SS
**Device:** earshot
**Duration:** Xh Xm Xs
**Processed:** YYYY-MM-DD HH:MM:SS

---

[MM:SS] segment text
[HH:MM:SS] segment text (for timestamps beyond one hour)
```

This format was chosen to ensure cross-tool compatibility. earshot-tui can detect a pre-existing `transcript.md` and skip its own transcription step for sessions already processed on-device.

### 5. Enabled by default

Transcription is enabled by default. The installer installs faster-whisper and downloads the default model as part of the standard setup. Users who do not want transcription can disable it with `transcription.enabled = false` or pass `--no-transcription` to the installer.

Default model: `tiny.en` (INT8). Suitable for both Pi 4B and Pi Zero 2W. Users may configure `base.en` on Pi 4B for better accuracy.

## Consequences

- faster-whisper is installed as a Python package via pip. CTranslate2 wheels include optimized ARM64 binaries; no build step is required.
- Quantized model files are stored on the SD card (e.g. `~/.local/share/earshot/models/`). The tiny.en INT8 model is ~35 MB; base.en INT8 is ~60 MB.
- A new device state is introduced: **Transcribing** — idle with transcription queue active. LED: amber slow pulsate. This state is transparent on the ReSpeaker HAT (LED only); the Whisplay HAT LCD shows queue depth and current session.
- Transcription of a 15-minute session takes approximately 3–6 minutes on Pi 4B (tiny.en) and 7–18 minutes on Pi Zero 2W. Long sessions on Pi Zero 2W may queue for hours; this is expected and documented.
- Interrupted transcription (power loss or new recording) leaves no partial output. The session remains queued and is retried from the beginning.
- USB offload is not gated on transcription completion. Sessions are offloaded regardless of transcription state. A future option (`storage.require_transcript_before_offload`) may gate offload on transcript availability — deferred to a later release.
- Recording pipeline (as of v0.2.2): WAV chunks are preserved during recording, concatenated at the end of recording, then encoded to opus. WAV files remain on the device (USB offload skips them). Orphaned WAV recovery (NFR-2) still applies: any `recording-*.wav` without corresponding `.opus` file is recovered on boot.
- `processing.md` is updated: the statement "no transcription is performed on-device" is superseded by this ADR for users who opt in.
