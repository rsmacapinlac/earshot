"""Write PCM to a WAV file during capture."""

from __future__ import annotations

import wave
from pathlib import Path


class StereoWavWriter:
    def __init__(self, path: Path, sample_rate: int, channels: int) -> None:
        self._path = path
        self._wf = wave.open(str(path), "wb")
        self._wf.setnchannels(channels)
        self._wf.setsampwidth(2)
        self._wf.setframerate(sample_rate)

    def write_frames(self, pcm: bytes) -> None:
        self._wf.writeframes(pcm)

    def close(self) -> None:
        self._wf.close()
