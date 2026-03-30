"""Load and validate `config.toml` (installer-generated or hand-written)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


def _load_toml(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    try:
        import tomllib  # Python 3.11+

        return tomllib.loads(data.decode())
    except ModuleNotFoundError:  # pragma: no cover
        import tomli

        return tomli.loads(data.decode())


@dataclass(frozen=True, slots=True)
class AudioConfig:
    """When ``alsa_pcm`` is set, capture uses ``arecord`` (recommended on Pi + ReSpeaker)."""

    sample_rate: int
    channels: int
    bit_depth: int
    opus_bitrate: int
    input_device_index: int | None = None
    alsa_pcm: str | None = None


@dataclass(frozen=True, slots=True)
class RecordingConfig:
    max_duration_seconds: float
    min_duration_seconds: float
    shutdown_hold_seconds: float


@dataclass(frozen=True, slots=True)
class StorageConfig:
    data_dir: Path
    disk_threshold_percent: float
    recordings_dir: Path


@dataclass(frozen=True, slots=True)
class ApiConfig:
    endpoint: str
    secret: str | None


@dataclass(frozen=True, slots=True)
class AppConfig:
    audio: AudioConfig
    recording: RecordingConfig
    storage: StorageConfig
    api: ApiConfig
    config_path: Path


def config_file_path(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    env = os.environ.get("EARSHOT_CONFIG", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / "config.toml").resolve()


def load_config(explicit_path: Path | None = None) -> AppConfig:
    path = config_file_path(explicit_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Earshot config not found: {path}. "
            "Set EARSHOT_CONFIG or pass --config, or run from the install directory."
        )
    raw = _load_toml(path)
    audio = _section(raw, "audio")
    recording = _section(raw, "recording")
    storage = _section(raw, "storage")
    api = _section(raw, "api")
    data_dir = Path(str(storage["data_dir"])).expanduser().resolve()
    recordings_dir_raw = storage.get("recordings_dir")
    recordings_dir = (
        Path(str(recordings_dir_raw)).expanduser().resolve()
        if recordings_dir_raw
        else data_dir / "recordings"
    )
    return AppConfig(
        audio=AudioConfig(
            sample_rate=int(audio["sample_rate"]),
            channels=int(audio["channels"]),
            bit_depth=int(audio["bit_depth"]),
            opus_bitrate=int(audio["opus_bitrate"]),
            input_device_index=(
                int(audio["input_device_index"])
                if audio.get("input_device_index") is not None
                else None
            ),
            alsa_pcm=(
                str(audio["alsa_pcm"]).strip()
                if audio.get("alsa_pcm") is not None
                and str(audio["alsa_pcm"]).strip()
                else None
            ),
        ),
        recording=RecordingConfig(
            max_duration_seconds=float(recording["max_duration_seconds"]),
            min_duration_seconds=float(recording["min_duration_seconds"]),
            shutdown_hold_seconds=float(recording["shutdown_hold_seconds"]),
        ),
        storage=StorageConfig(
            data_dir=data_dir,
            disk_threshold_percent=float(storage["disk_threshold_percent"]),
            recordings_dir=recordings_dir,
        ),
        api=ApiConfig(
            endpoint=str(api.get("endpoint") or "").strip(),
            secret=(str(api["secret"]).strip() if api.get("secret") else None),
        ),
        config_path=path,
    )


def _section(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
    block = raw.get(name)
    if not isinstance(block, Mapping):
        raise KeyError(f"config.toml missing [{name}] table")
    return dict(block)
