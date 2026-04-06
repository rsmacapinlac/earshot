"""Implicit transcription queue derived from filesystem state (FR-14).

A session is *pending* when its directory contains one or more ``.opus``
files but no ``transcript.md``.  Sessions are returned FIFO by directory
name (which encodes the recording timestamp).
"""

from __future__ import annotations

from pathlib import Path


def pending_sessions(recordings_dir: Path) -> list[Path]:
    """Return session directories pending transcription, oldest first."""
    if not recordings_dir.exists():
        return []
    result = []
    for d in sorted(recordings_dir.iterdir()):
        if not d.is_dir():
            continue
        if any(d.glob("*.opus")) and not (d / "transcript.md").exists():
            result.append(d)
    return result
