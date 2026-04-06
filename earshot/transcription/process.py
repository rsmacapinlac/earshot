"""Transcription process: concat .opus files → whisper-cli → segment list (FR-15).

Pipeline (two temp files, both cleaned up after use):

    ffmpeg -f concat -safe 0 -i <filelist.txt> -ar 16000 -ac 1 -f wav <tmp.wav>
    whisper-cli --model <path> --language en --threads N -f <tmp.wav>

Why two temp files:
- The concat demuxer (not the concat: protocol) is required because OGG/Opus
  containers cannot be raw-concatenated — the concat: protocol corrupts streams.
- whisper-cli calls fseek() when parsing WAV, so piping via /dev/stdin fails.
  A real file is required.

whisper-cli writes timestamped segments to stdout in the format::

    [HH:MM:SS.mmm --> HH:MM:SS.mmm]  segment text
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

_log = logging.getLogger(__name__)

_SEGMENT_RE = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\]\s+(.*)"
)


def _ts_to_ms(ts: str) -> int:
    """Parse 'HH:MM:SS.mmm' → milliseconds."""
    h, m, rest = ts.split(":")
    s, ms = rest.split(".")
    return int(h) * 3_600_000 + int(m) * 60_000 + int(s) * 1_000 + int(ms)


def transcribe_session(
    session_dir: Path,
    model_path: Path,
    threads: int,
    cancel: threading.Event,
) -> list[dict] | None:
    """Transcribe all ``.opus`` files in *session_dir* using whisper-cli.

    Returns a list of ``{"from_ms": int, "to_ms": int, "text": str}`` dicts
    on success, an empty list if the audio yields no speech, or ``None`` on
    failure or cancellation.

    On cancellation (*cancel* is set), both subprocesses are terminated and
    ``None`` is returned.  The session remains pending for the next idle window.
    """
    opus_files = sorted(session_dir.glob("*.opus"))
    if not opus_files:
        _log.warning("transcribe_session: no .opus files in %s", session_dir.name)
        return None

    if not model_path.exists():
        _log.error("Whisper model not found: %s", model_path)
        return None

    _log.info(
        "Transcribing %s (%d chunk(s)) with model %s",
        session_dir.name,
        len(opus_files),
        model_path.name,
    )

    # Two temp files: a concat demuxer filelist and the decoded WAV.
    # whisper-cli calls fseek() when reading WAV, so /dev/stdin cannot be used.
    filelist_fd, filelist_path = tempfile.mkstemp(suffix=".txt", prefix="earshot-concat-")
    wav_fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="earshot-wav-")
    os.close(wav_fd)  # ffmpeg will open it by path
    try:
        with os.fdopen(filelist_fd, "w") as fh:
            for f in opus_files:
                fh.write(f"file '{f}'\n")

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", filelist_path,
            "-ar", "16000", "-ac", "1",
            wav_path,
        ]
        whisper_cmd = [
            "whisper-cli",
            "--model", str(model_path),
            "--language", "en",
            "--threads", str(threads),
            "-f", wav_path,
        ]

        try:
            # Phase 1: decode to WAV (cancellable)
            ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stderr=subprocess.DEVNULL)
            while ffmpeg_proc.poll() is None:
                if cancel.is_set():
                    _log.info("Cancelling transcription of %s (ffmpeg)", session_dir.name)
                    ffmpeg_proc.terminate()
                    try:
                        ffmpeg_proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        ffmpeg_proc.kill()
                    return None
                time.sleep(0.5)

            if ffmpeg_proc.returncode != 0:
                _log.error(
                    "ffmpeg exited %d for %s",
                    ffmpeg_proc.returncode,
                    session_dir.name,
                )
                return None

            # Phase 2: transcribe WAV (cancellable)
            whisper_proc = subprocess.Popen(
                whisper_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            while whisper_proc.poll() is None:
                if cancel.is_set():
                    _log.info("Cancelling transcription of %s (whisper)", session_dir.name)
                    whisper_proc.terminate()
                    try:
                        whisper_proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        whisper_proc.kill()
                    return None
                time.sleep(0.5)

            stdout_data = whisper_proc.stdout.read()  # type: ignore[union-attr]

            if whisper_proc.returncode != 0:
                _log.error(
                    "whisper-cli exited %d for %s",
                    whisper_proc.returncode,
                    session_dir.name,
                )
                return None

        except FileNotFoundError as exc:
            _log.error("Binary not found (%s) — is whisper-cli installed?", exc)
            return None
        except Exception as exc:
            _log.error("Transcription subprocess error for %s: %s", session_dir.name, exc)
            return None

    finally:
        os.unlink(filelist_path)
        try:
            os.unlink(wav_path)
        except FileNotFoundError:
            pass  # ffmpeg may not have created it if it failed early

    segments: list[dict] = []
    for line in stdout_data.decode("utf-8", errors="replace").splitlines():
        m = _SEGMENT_RE.match(line.strip())
        if m:
            text = m.group(3).strip()
            if text:
                segments.append({
                    "from_ms": _ts_to_ms(m.group(1)),
                    "to_ms": _ts_to_ms(m.group(2)),
                    "text": text,
                })

    _log.info(
        "Transcription complete: %s — %d segment(s)", session_dir.name, len(segments)
    )
    return segments
