"""Transcription process: WAV file → faster_whisper → segment list (FR-15).

Pipeline:

    faster_whisper.WhisperModel.transcribe(session.wav)

The session.wav file is pre-concatenated from individual recording chunks
at the end of the recording session.

faster_whisper yields timestamped Segment objects with .start, .end (float seconds), .text.
Segments are converted to {"from_ms": int, "to_ms": int, "text": str} format.
"""

from __future__ import annotations

import logging
from pathlib import Path

from faster_whisper import WhisperModel

_log = logging.getLogger(__name__)


def transcribe_session(
    session_dir: Path,
    model: WhisperModel,
    cancel: threading.Event,
) -> list[dict] | None:
    """Transcribe the pre-concatenated session.wav file using faster_whisper.

    Returns a list of ``{"from_ms": int, "to_ms": int, "text": str}`` dicts
    on success, an empty list if the audio yields no speech, or ``None`` on
    failure or cancellation.

    On cancellation (*cancel* is set), transcription stops and ``None`` is returned.
    The session remains pending for the next idle window.
    """
    opus_path = session_dir / "session.opus"
    if not opus_path.exists():
        _log.warning("transcribe_session: session.opus not found in %s", session_dir.name)
        return None

    _log.info("Transcribing %s", session_dir.name)

    # Check for cancellation before calling transcribe
    if cancel.is_set():
        return None

    # Transcribe opus file with faster_whisper (lazy segment iterator)
    # faster_whisper uses ffmpeg for audio decoding, so it can read opus directly
    try:
        segments_iter, _info = model.transcribe(str(opus_path), language="en", beam_size=5)
    except Exception as exc:
        _log.error("faster_whisper transcribe() failed for %s: %s", session_dir.name, exc)
        return None

    # Segment iteration. The generator is lazy — ctranslate2 reads the file during iteration.
    _NOISE_TOKENS = {"[BLANK_AUDIO]", "[Music]", "[Applause]", "[Laughter]"}

    segments: list[dict] = []
    try:
        for seg in segments_iter:
            if cancel.is_set():
                _log.info("Cancelling transcription of %s (segment loop)", session_dir.name)
                return None
            text = seg.text.strip()
            if text and text not in _NOISE_TOKENS:
                segments.append({
                    "from_ms": int(seg.start * 1000),
                    "to_ms": int(seg.end * 1000),
                    "text": text,
                })
    except Exception as exc:
        _log.error("Segment iteration failed for %s: %s", session_dir.name, exc)
        return None

    _log.info(
        "Transcription complete: %s — %d segment(s)", session_dir.name, len(segments)
    )
    return segments
