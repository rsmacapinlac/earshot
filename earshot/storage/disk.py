"""Disk usage checks (FR-6 disk threshold)."""

from __future__ import annotations

import shutil
from pathlib import Path


def disk_usage_percent(path: Path) -> float:
    usage = shutil.disk_usage(path)
    if usage.total <= 0:
        return 100.0
    return 100.0 * (usage.used / usage.total)


def is_over_disk_threshold(path: Path, threshold_percent: float) -> bool:
    return disk_usage_percent(path) >= threshold_percent
