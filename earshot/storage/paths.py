"""Filesystem layout under `storage.recordings_dir`."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from earshot.config import AppConfig


def recordings_root(cfg: AppConfig) -> Path:
    return cfg.storage.recordings_dir


def new_recording_stamp(now: datetime | None = None) -> str:
    dt = now or datetime.now()
    return dt.strftime("%Y%m%dT%H%M%S")


def recording_directory(cfg: AppConfig, stamp: str) -> Path:
    return recordings_root(cfg) / stamp
