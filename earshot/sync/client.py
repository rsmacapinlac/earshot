"""Opportunistic upload of `audio.opus` to the API (FR-7)."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import httpx

from earshot.storage import db as dbmod

_log = logging.getLogger(__name__)


def try_sync_recording(
    endpoint: str,
    directory: Path,
    *,
    recording_id: str,
    secret: str | None,
) -> bool:
    """Upload audio.opus to the API. Returns True if the upload succeeded."""
    if not endpoint:
        return True

    base = endpoint.rstrip("/")
    headers: dict[str, str] = {}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"

    opus_path = directory / "audio.opus"
    if not opus_path.is_file():
        _log.warning("audio.opus not found for %s — skipping", recording_id)
        return False

    with httpx.Client(timeout=120.0) as client:
        try:
            r = client.post(
                f"{base}/recordings/{recording_id}/audio",
                headers=headers,
                files={"file": (opus_path.name, opus_path.read_bytes(), "audio/ogg")},
            )
            r.raise_for_status()
            return True
        except (httpx.HTTPError, OSError) as exc:
            _log.warning("Audio upload failed for %s: %s", recording_id, exc)
            return False


def sync_pending_uploads(
    conn: sqlite3.Connection,
    endpoint: str,
    secret: str | None,
) -> None:
    rows = dbmod.list_uploads_pending(conn)
    for row in rows:
        rid = str(row["recording_id"])
        directory = Path(str(row["directory"]))
        if endpoint.strip():
            dbmod.update_upload_state(conn, rid, increment_retry=True)
        ok = try_sync_recording(endpoint, directory, recording_id=rid, secret=secret)
        dbmod.update_upload_state(
            conn,
            rid,
            audio_state="complete" if ok else "failed",
            increment_retry=False,
            touch_attempt_time=bool(endpoint.strip()),
        )
