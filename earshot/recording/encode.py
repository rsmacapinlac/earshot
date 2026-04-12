"""Encode and concatenate WAV files via ffmpeg (FR-6)."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

_log = logging.getLogger(__name__)


def wav_to_opus_mono(
    wav_path: Path,
    opus_path: Path,
    *,
    sample_rate: int,
    bitrate_kbps: int,
    ignore_header_length: bool = False,
) -> None:
    """Encode WAV to Opus mono (legacy, used for crash recovery)."""
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


def wav_to_opus_stereo(
    wav_path: Path,
    opus_path: Path,
    *,
    sample_rate: int,
    bitrate_kbps: int,
) -> None:
    """Encode WAV to Opus stereo for offload."""
    opus_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(wav_path),
        "-ac",
        "2",
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
    _log.info("Encoded %s to opus stereo: %s", wav_path.name, opus_path.name)


def concat_wav_files(
    session_dir: Path,
    output_path: Path,
) -> None:
    """Concatenate all recording-*.wav files in session_dir into a single output WAV.

    Uses ffmpeg's concat demuxer to properly concatenate OGG/Opus-encoded audio
    without corrupting the container. Creates a temporary filelist.
    """
    wav_files = sorted(session_dir.glob("recording-*.wav"))
    if not wav_files:
        raise RuntimeError(f"No WAV files found in {session_dir}")

    # Create temporary filelist for ffmpeg concat demuxer
    filelist_fd, filelist_path = tempfile.mkstemp(suffix=".txt", prefix="earshot-concat-")
    try:
        with open(filelist_fd, "w") as fh:
            for wav_file in wav_files:
                fh.write(f"file '{wav_file.absolute()}'\n")

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            "-f", "concat",
            "-safe", "0",
            "-i", filelist_path,
            "-c", "copy",  # Copy without re-encoding
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg concat failed ({proc.returncode}): {proc.stderr or proc.stdout}"
            )
        _log.info("Concatenated %d WAV files into %s", len(wav_files), output_path.name)
    finally:
        Path(filelist_path).unlink(missing_ok=True)
