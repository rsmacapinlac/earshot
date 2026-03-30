"""Opportunistic upload of `audio.mp3` and `result.json` (FR-7)."""

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
    mp3_done: bool,
    result_done: bool,
) -> tuple[bool, bool]:
    """Returns (mp3_complete, result_complete) after best-effort upload."""
    if not endpoint:
        return True, True

    base = endpoint.rstrip("/")
    headers: dict[str, str] = {}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"

    mp3_path = directory / "audio.mp3"
    json_path = directory / "result.json"

    mp3_ok = mp3_done
    result_ok = result_done

    with httpx.Client(timeout=120.0) as client:
        if not mp3_ok and mp3_path.is_file():
            try:
                r = client.post(
                    f"{base}/recordings/{recording_id}/audio",
                    headers=headers,
                    files={"file": (mp3_path.name, mp3_path.read_bytes(), "audio/mpeg")},
                )
                r.raise_for_status()
                mp3_ok = True
            except (httpx.HTTPError, OSError) as exc:
                _log.warning("MP3 upload failed for %s: %s", recording_id, exc)

        if not result_ok and json_path.is_file():
            try:
                r = client.post(
                    f"{base}/recordings/{recording_id}/result",
                    headers=headers,
                    files={"file": (json_path.name, json_path.read_bytes(), "application/json")},
                )
                r.raise_for_status()
                result_ok = True
            except (httpx.HTTPError, OSError) as exc:
                _log.warning("result.json upload failed for %s: %s", recording_id, exc)

    return mp3_ok, result_ok


def sync_pending_uploads(
    conn: sqlite3.Connection,
    endpoint: str,
    secret: str | None,
) -> None:
    rows = dbmod.list_uploads_pending(conn)
    for row in rows:
        rid = str(row["recording_id"])
        directory = Path(str(row["directory"]))
        mp3_done = str(row["mp3_state"]) == "complete"
        result_done = str(row["result_state"]) == "complete"
        if endpoint.strip():
            dbmod.update_upload_states(conn, rid, increment_retry=True)
        mp3_ok, res_ok = try_sync_recording(
            endpoint,
            directory,
            recording_id=rid,
            secret=secret,
            mp3_done=mp3_done,
            result_done=result_done,
        )
        dbmod.update_upload_states(
            conn,
            rid,
            mp3_state="complete" if mp3_ok else "failed",
            result_state="complete" if res_ok else "failed",
            increment_retry=False,
            touch_attempt_time=bool(endpoint.strip()),
        )
