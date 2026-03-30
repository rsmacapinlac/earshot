"""SQLite state store (ADR 0009)."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 3


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
    if version == 0:
        conn.executescript(
            """
            CREATE TABLE recordings (
                id TEXT PRIMARY KEY,
                recorded_at TEXT NOT NULL,
                directory TEXT NOT NULL UNIQUE,
                duration_seconds REAL NOT NULL
            );

            CREATE TABLE uploads (
                recording_id TEXT PRIMARY KEY,
                audio_state TEXT NOT NULL DEFAULT 'pending',
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
            """
        )
    elif version == 1:
        # Migrate from v1: drop processing columns from recordings, simplify uploads.
        conn.executescript(
            """
            ALTER TABLE recordings DROP COLUMN processing_state;
            ALTER TABLE recordings DROP COLUMN processing_started_at;
            ALTER TABLE recordings DROP COLUMN processing_completed_at;
            ALTER TABLE recordings DROP COLUMN processing_duration_seconds;
            ALTER TABLE recordings DROP COLUMN error;

            ALTER TABLE uploads DROP COLUMN result_state;
            ALTER TABLE uploads RENAME COLUMN mp3_state TO audio_state;
            """
        )
    if version < 3:
        # Migrate from v2: add audio_filename so multiple chunks can share a session
        # directory.  Recreate recordings with the new unique constraint on
        # (directory, audio_filename) instead of directory alone.
        conn.executescript(
            """
            CREATE TABLE recordings_v3 (
                id TEXT PRIMARY KEY,
                recorded_at TEXT NOT NULL,
                directory TEXT NOT NULL,
                audio_filename TEXT NOT NULL DEFAULT 'audio.opus',
                duration_seconds REAL NOT NULL,
                UNIQUE (directory, audio_filename)
            );
            INSERT INTO recordings_v3 (id, recorded_at, directory, audio_filename, duration_seconds)
                SELECT id, recorded_at, directory, 'audio.opus', duration_seconds
                FROM recordings;
            DROP TABLE recordings;
            ALTER TABLE recordings_v3 RENAME TO recordings;
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
    audio_filename: str = "audio.opus",
    duration_seconds: float,
) -> str:
    rec_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO recordings (id, recorded_at, directory, audio_filename, duration_seconds)
        VALUES (?, ?, ?, ?, ?)
        """,
        (rec_id, recorded_at, str(directory), audio_filename, duration_seconds),
    )
    conn.execute(
        """
        INSERT INTO uploads (recording_id, audio_state, retry_count, last_attempted_at)
        VALUES (?, 'pending', 0, NULL)
        """,
        (rec_id,),
    )
    conn.commit()
    return rec_id


def list_uploads_pending(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT u.recording_id, u.audio_state, r.directory, r.audio_filename
        FROM uploads u
        JOIN recordings r ON r.id = u.recording_id
        WHERE u.audio_state != 'complete'
        ORDER BY r.recorded_at ASC
        """
    )
    return [dict(row) for row in cur.fetchall()]


def update_upload_state(
    conn: sqlite3.Connection,
    recording_id: str,
    *,
    audio_state: str | None = None,
    increment_retry: bool = False,
    touch_attempt_time: bool = True,
) -> None:
    sets: list[str] = []
    args: list[Any] = []
    if touch_attempt_time:
        sets.append("last_attempted_at = ?")
        args.append(utc_now_iso())
    if audio_state is not None:
        sets.append("audio_state = ?")
        args.append(audio_state)
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
