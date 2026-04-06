"""Write whisper-cli segment output to transcript.md (FR-16).

Output format (earshot-tui compatible)::

    # Recording — YYYY-MM-DD HH:MM:SS
    **Duration:** Xh Xm Xs
    **Processed:** YYYY-MM-DD HH:MM:SS

    ---

    [MM:SS] segment text
    [HH:MM:SS] segment text
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def _fmt_timestamp(ms: int) -> str:
    """Format milliseconds as ``[MM:SS]`` or ``[HH:MM:SS]`` depending on length."""
    total_s = ms // 1000
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    if h:
        return f"[{h:02d}:{m:02d}:{s:02d}]"
    return f"[{m:02d}:{s:02d}]"


def _fmt_duration(total_ms: int) -> str:
    """Format milliseconds as ``Xh Xm Xs``."""
    total_s = total_ms // 1000
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    parts: list[str] = []
    if h:
        parts.append(f"{h}h")
    parts.append(f"{m}m")  # always include minutes
    parts.append(f"{s}s")
    return " ".join(parts)


def write_transcript(
    session_dir: Path,
    segments: list[dict],
    *,
    processed_at: datetime | None = None,
) -> Path:
    """Write ``transcript.md`` to *session_dir* and return its path.

    *segments* is a list of ``{"from_ms": int, "to_ms": int, "text": str}``
    dicts as returned by :func:`~earshot.transcription.process.transcribe_session`.
    An empty list produces a header-only transcript (valid for silent sessions).
    """
    now = processed_at or datetime.now()

    try:
        session_dt = datetime.strptime(session_dir.name, "%Y%m%dT%H%M%S")
        recording_header = session_dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        recording_header = session_dir.name

    duration_ms = segments[-1]["to_ms"] if segments else 0
    duration_str = _fmt_duration(duration_ms)
    processed_str = now.strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# Recording — {recording_header}",
        f"**Duration:** {duration_str}",
        f"**Processed:** {processed_str}",
        "",
        "---",
        "",
    ]
    for seg in segments:
        lines.append(f"{_fmt_timestamp(seg['from_ms'])} {seg['text']}")

    out_path = session_dir / "transcript.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path
