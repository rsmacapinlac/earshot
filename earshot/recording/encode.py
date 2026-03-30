"""Encode temporary WAV to Opus via ffmpeg (FR-6)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def wav_to_opus_mono(
    wav_path: Path,
    opus_path: Path,
    *,
    sample_rate: int,
    bitrate_kbps: int,
    ignore_header_length: bool = False,
) -> None:
    opus_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if ignore_header_length:
        # WAV files written by Python's wave module have zeroed chunk-size fields
        # if the process crashed before close(). This flag tells the WAV decoder to
        # ignore the declared data-chunk length and read audio until EOF instead.
        cmd += ["-ignore_length", "1"]
    cmd += [
        "-i",
        str(wav_path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-c:a",
        "libopus",
        "-b:a",
        f"{bitrate_kbps}k",
        str(opus_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed ({proc.returncode}): {proc.stderr or proc.stdout}"
        )
