"""SQLite state store (ADR 0009)."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True, slots=True)
class RecordingRow:
    id: str
    recorded_at: str
    directory: str
    duration_seconds: float
    processing_state: str
    processing_started_at: str | None
    processing_completed_at: str | None
    processing_duration_seconds: float | None
    error: str | None


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Shared across threads (e.g. sync worker); EarshotApp serializes access with a lock.
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    version_row = conn.execute("PRAGMA user_version").fetchone()
    version = int(version_row[0]) if version_row else 0
    if version >= SCHEMA_VERSION:
        return
    if version != 0:
        raise RuntimeError(
            f"Unsupported earshot.db schema user_version={version}; "
            f"this code expects {SCHEMA_VERSION}. Backup and migrate manually."
        )
    conn.executescript(
        """
        CREATE TABLE recordings (
            id TEXT PRIMARY KEY,
            recorded_at TEXT NOT NULL,
            directory TEXT NOT NULL UNIQUE,
            duration_seconds REAL NOT NULL,
            processing_state TEXT NOT NULL,
            processing_started_at TEXT,
            processing_completed_at TEXT,
            processing_duration_seconds REAL,
            error TEXT
        );

        CREATE TABLE uploads (
            recording_id TEXT PRIMARY KEY,
            mp3_state TEXT NOT NULL DEFAULT 'pending',
            result_state TEXT NOT NULL DEFAULT 'pending',
            retry_count INTEGER NOT NULL DEFAULT 0,
            last_attempted_at TEXT,
            FOREIGN KEY (recording_id) REFERENCES recordings(id)
        );

        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT NOT NULL,
            recording_id TEXT,
            level TEXT NOT NULL,
            message TEXT NOT NULL
        );

        CREATE INDEX idx_recordings_processing ON recordings(processing_state);
        """
    )
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def log_event(
    conn: sqlite3.Connection,
    message: str,
    *,
    level: str = "info",
    recording_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO events (recorded_at, recording_id, level, message) VALUES (?, ?, ?, ?)",
        (utc_now_iso(), recording_id, level, message),
    )
    conn.commit()


def insert_recording_pending(
    conn: sqlite3.Connection,
    *,
    recorded_at: str,
    directory: Path,
    duration_seconds: float,
) -> str:
    rec_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO recordings (
            id, recorded_at, directory, duration_seconds,
            processing_state, processing_started_at, processing_completed_at,
            processing_duration_seconds, error
        ) VALUES (?, ?, ?, ?, 'pending', NULL, NULL, NULL, NULL)
        """,
        (rec_id, recorded_at, str(directory), duration_seconds),
    )
    conn.execute(
        """
        INSERT INTO uploads (recording_id, mp3_state, result_state, retry_count, last_attempted_at)
        VALUES (?, 'pending', 'pending', 0, NULL)
        """,
        (rec_id,),
    )
    conn.commit()
    return rec_id


def list_recordings_needing_processing(conn: sqlite3.Connection) -> list[RecordingRow]:
    cur = conn.execute(
        """
        SELECT id, recorded_at, directory, duration_seconds, processing_state,
               processing_started_at, processing_completed_at,
               processing_duration_seconds, error
        FROM recordings
        WHERE processing_state IN ('pending', 'processing')
        ORDER BY recorded_at ASC
        """
    )
    rows: list[RecordingRow] = []
    for r in cur.fetchall():
        rows.append(
            RecordingRow(
                id=str(r["id"]),
                recorded_at=str(r["recorded_at"]),
                directory=str(r["directory"]),
                duration_seconds=float(r["duration_seconds"]),
                processing_state=str(r["processing_state"]),
                processing_started_at=(
                    str(r["processing_started_at"])
                    if r["processing_started_at"] is not None
                    else None
                ),
                processing_completed_at=(
                    str(r["processing_completed_at"])
                    if r["processing_completed_at"] is not None
                    else None
                ),
                processing_duration_seconds=(
                    float(r["processing_duration_seconds"])
                    if r["processing_duration_seconds"] is not None
                    else None
                ),
                error=str(r["error"]) if r["error"] is not None else None,
            )
        )
    return rows


def reset_stale_processing(conn: sqlite3.Connection) -> int:
    """Treat interrupted 'processing' rows as pending again (NFR-4)."""
    cur = conn.execute(
        """
        UPDATE recordings
        SET processing_state = 'pending',
            processing_started_at = NULL
        WHERE processing_state = 'processing'
        """
    )
    conn.commit()
    return cur.rowcount


def mark_processing_started(conn: sqlite3.Connection, recording_id: str) -> None:
    conn.execute(
        """
        UPDATE recordings
        SET processing_state = 'processing',
            processing_started_at = ?,
            error = NULL
        WHERE id = ?
        """,
        (utc_now_iso(), recording_id),
    )
    conn.commit()


def mark_processing_complete(
    conn: sqlite3.Connection,
    recording_id: str,
    *,
    duration_seconds: float,
) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE recordings
        SET processing_state = 'complete',
            processing_completed_at = ?,
            processing_duration_seconds = ?,
            error = NULL
        WHERE id = ?
        """,
        (now, duration_seconds, recording_id),
    )
    conn.commit()


def mark_processing_failed(
    conn: sqlite3.Connection,
    recording_id: str,
    error: str,
) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE recordings
        SET processing_state = 'failed',
            processing_completed_at = ?,
            error = ?
        WHERE id = ?
        """,
        (now, error, recording_id),
    )
    conn.commit()


def list_uploads_pending(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT u.recording_id, u.mp3_state, u.result_state, r.directory
        FROM uploads u
        JOIN recordings r ON r.id = u.recording_id
        WHERE r.processing_state = 'complete'
          AND NOT (u.mp3_state = 'complete' AND u.result_state = 'complete')
        ORDER BY r.recorded_at ASC
        """
    )
    return [dict(row) for row in cur.fetchall()]


def update_upload_states(
    conn: sqlite3.Connection,
    recording_id: str,
    *,
    mp3_state: str | None = None,
    result_state: str | None = None,
    increment_retry: bool = False,
    touch_attempt_time: bool = True,
) -> None:
    sets: list[str] = []
    args: list[Any] = []
    if touch_attempt_time:
        sets.append("last_attempted_at = ?")
        args.append(utc_now_iso())
    if mp3_state is not None:
        sets.append("mp3_state = ?")
        args.append(mp3_state)
    if result_state is not None:
        sets.append("result_state = ?")
        args.append(result_state)
    if increment_retry:
        sets.append("retry_count = retry_count + 1")
    if not sets:
        return
    args.append(recording_id)
    conn.execute(
        f"UPDATE uploads SET {', '.join(sets)} WHERE recording_id = ?",
        args,
    )
    conn.commit()
