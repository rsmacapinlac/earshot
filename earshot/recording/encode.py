"""Encode temporary WAV to MP3 via ffmpeg (FR-6)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def wav_to_mp3_mono(
    wav_path: Path,
    mp3_path: Path,
    *,
    sample_rate: int,
    bitrate_kbps: int,
) -> None:
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(wav_path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-b:a",
        f"{bitrate_kbps}k",
        str(mp3_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed ({proc.returncode}): {proc.stderr or proc.stdout}"
        )
