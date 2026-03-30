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
    sample_rate: int
    channels: int
    bit_depth: int
    mp3_bitrate: int
    input_device_index: int | None = None


@dataclass(frozen=True, slots=True)
class RecordingConfig:
    max_duration_seconds: float
    min_duration_seconds: float
    shutdown_hold_seconds: float


@dataclass(frozen=True, slots=True)
class ProcessingConfig:
    whisper_model: str


@dataclass(frozen=True, slots=True)
class StorageConfig:
    data_dir: Path
    disk_threshold_percent: float


@dataclass(frozen=True, slots=True)
class ApiConfig:
    endpoint: str
    secret: str | None


@dataclass(frozen=True, slots=True)
class AppConfig:
    audio: AudioConfig
    recording: RecordingConfig
    processing: ProcessingConfig
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
    processing = _section(raw, "processing")
    storage = _section(raw, "storage")
    api = _section(raw, "api")
    data_dir = Path(str(storage["data_dir"])).expanduser().resolve()
    return AppConfig(
        audio=AudioConfig(
            sample_rate=int(audio["sample_rate"]),
            channels=int(audio["channels"]),
            bit_depth=int(audio["bit_depth"]),
            mp3_bitrate=int(audio["mp3_bitrate"]),
            input_device_index=(
                int(audio["input_device_index"])
                if audio.get("input_device_index") is not None
                else None
            ),
        ),
        recording=RecordingConfig(
            max_duration_seconds=float(recording["max_duration_seconds"]),
            min_duration_seconds=float(recording["min_duration_seconds"]),
            shutdown_hold_seconds=float(recording["shutdown_hold_seconds"]),
        ),
        processing=ProcessingConfig(
            whisper_model=str(processing["whisper_model"]),
        ),
        storage=StorageConfig(
            data_dir=data_dir,
            disk_threshold_percent=float(storage["disk_threshold_percent"]),
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
