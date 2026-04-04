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

### 1. Engine: whisper.cpp with GGML quantized models

whisper.cpp is a C/C++ port of OpenAI Whisper compiled to ARM64 native binaries with NEON SIMD. It is invoked as a subprocess from the existing Python application.

Key reasons over alternatives:

- **No Python overhead.** whisper.cpp is a single compiled binary. On the Pi Zero 2W, Python framework overhead (~100–150 MB) is unacceptable; whisper.cpp avoids it entirely.
- **GGML Q5_1 quantization.** The quantized tiny.en model is 31 MB on disk and ~130 MB at runtime — the only Whisper variant that fits within the Pi Zero 2W's budget. Unquantized float16 models require ~2–3× more RAM.
- **Proven ARM NEON path.** NEON SIMD is the default code path on ARM64; no AVX dependency. Performance is well-characterised on Raspberry Pi hardware.
- **Model format flexibility.** GGML supports Q4, Q5, and Q8 quantization levels; the installer can offer a model choice without changing the integration.

**faster-whisper** (CTranslate2, Python): offers a cleaner Python API and built-in VAD, but adds ~100 MB Python + library overhead and historically underperforms whisper.cpp on ARM without correct backend configuration (SYSTRAN/faster-whisper#38). Not viable on Pi Zero 2W.

**Vosk**: lower accuracy (~15–20% WER vs Whisper's ~5–8% on clean English) with a similar RAM footprint. Retained as a documented fallback if whisper.cpp proves unworkable on a specific hardware configuration.

**openai/whisper (PyTorch)**: 3–5× slower than whisper.cpp, ~500 MB RAM minimum before framework overhead. Ruled out on both devices.

### 2. Session-level transcription, not chunk-level

Transcription operates on the full session, not on individual chunks. All `.opus` files in a session directory are concatenated via `ffmpeg` and piped directly to whisper.cpp — no intermediate file is written.

Chunk-level transcription was rejected because:

- Whisper processes audio in 30-second windows internally. When transcribing separate chunk files, the model loses context at every 15-minute boundary — words and sentences split across chunks are transcribed without continuity.
- Session-level transcription produces a single `transcript.md` with continuous timestamps, which matches the earshot-tui output format and is more useful to the reader.
- Per-chunk `.txt` files require assembling a final transcript, complicating the state model.

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

Transcription is enabled by default. The installer installs whisper.cpp and downloads the default model as part of the standard setup. Users who do not want transcription can disable it with `transcription.enabled = false` or pass `--no-transcription` to the installer.

Default model: `tiny.en` (Q5_1). Suitable for both Pi 4B and Pi Zero 2W. Users may configure `base.en` on Pi 4B for better accuracy.

## Consequences

- whisper.cpp must be installed as part of the Earshot installer. Pre-built aarch64 binaries are available; build-from-source via cmake is the fallback.
- GGML model files are stored on the SD card (e.g. `~/.local/share/earshot/models/`). The tiny.en Q5_1 model is 31 MB; base.en Q5_1 is 57 MB.
- A new device state is introduced: **Transcribing** — idle with transcription queue active. LED: amber slow pulsate. This state is transparent on the ReSpeaker HAT (LED only); the Whisplay HAT LCD shows queue depth and current session.
- Transcription of a 15-minute session takes approximately 3–6 minutes on Pi 4B (tiny.en) and 7–18 minutes on Pi Zero 2W. Long sessions on Pi Zero 2W may queue for hours; this is expected and documented.
- Interrupted transcription (power loss or new recording) leaves no partial output. The session remains queued and is retried from the beginning.
- USB offload is not gated on transcription completion. Sessions are offloaded regardless of transcription state. A future option (`storage.require_transcript_before_offload`) may gate offload on transcript availability — deferred to a later release.
- `processing.md` is updated: the statement "no transcription is performed on-device" is superseded by this ADR for users who opt in.
