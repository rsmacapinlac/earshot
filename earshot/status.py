"""Status.json persistence for recordings (compatible with earshot-tui)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

StatusState = Literal["recorded", "encoded", "transcribed", "failed", "interrupted"]


class Status:
    """Recording status state saved to status.json.

    Compatible with earshot-tui's internal/recording/recording.go Status struct.
    """

    def __init__(
        self,
        status: StatusState,
        device: str,
        recorded_at: datetime,
        duration: float = 0.0,
        transcribed_at: datetime | None = None,
        error: str = "",
    ) -> None:
        self.status = status
        self.device = device
        self.recorded_at = recorded_at
        self.duration = duration
        self.transcribed_at = transcribed_at
        self.error = error

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        result = {
            "status": self.status,
            "device": self.device,
            "recorded_at": self.recorded_at.isoformat(),
            "duration": self.duration,
        }
        if self.transcribed_at is not None:
            result["transcribed_at"] = self.transcribed_at.isoformat()
        if self.error:
            result["error"] = self.error
        return result

    @staticmethod
    def from_dict(data: dict) -> Status:
        """Deserialize from JSON-compatible dict."""
        return Status(
            status=data["status"],
            device=data["device"],
            recorded_at=datetime.fromisoformat(data["recorded_at"]),
            duration=data.get("duration", 0.0),
            transcribed_at=(
                datetime.fromisoformat(data["transcribed_at"])
                if "transcribed_at" in data and data["transcribed_at"]
                else None
            ),
            error=data.get("error", ""),
        )


def save_status(recording_dir: Path, status: Status) -> None:
    """Atomically write status to recording_dir/status.json."""
    recording_dir.mkdir(parents=True, exist_ok=True)
    path = recording_dir / "status.json"
    tmp = path.with_suffix(".json.tmp")

    data = json.dumps(status.to_dict(), indent=2)
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def load_status(recording_dir: Path) -> Status | None:
    """Load status from recording_dir/status.json, or None if not found."""
    path = recording_dir / "status.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Status.from_dict(data)
