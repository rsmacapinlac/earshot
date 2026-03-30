"""Tests for multi-chunk recording session and orphaned WAV recovery."""

from __future__ import annotations

import sqlite3
import threading
import time
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from earshot.app import EarshotApp
from earshot.config import ApiConfig, AppConfig, AudioConfig, RecordingConfig, StorageConfig
from earshot.hal.bundle import Hal
from earshot.hal.stub import StubAudioCapture, StubButton, StubLED
from earshot.storage.db import connect, init_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config(
    tmp_path: Path,
    max_duration: float = 10.0,
    min_duration: float = 0.01,
) -> AppConfig:
    return AppConfig(
        audio=AudioConfig(
            sample_rate=16000,
            channels=2,
            bit_depth=16,
            opus_bitrate=32,
        ),
        recording=RecordingConfig(
            max_duration_seconds=max_duration,
            min_duration_seconds=min_duration,
            shutdown_hold_seconds=3.0,
        ),
        storage=StorageConfig(
            data_dir=tmp_path,
            disk_threshold_percent=90.0,
            recordings_dir=tmp_path / "recordings",
        ),
        api=ApiConfig(endpoint="", secret=None),
        config_path=tmp_path / "config.toml",
    )


def make_hal(button: StubButton) -> Hal:
    led = StubLED()
    return Hal(
        led=led,
        button=button,
        pi_led=None,
        animator=None,
        _audio_factory=lambda: StubAudioCapture(channels=2, sample_rate=16000),
        _on_close=lambda: None,
    )


def make_app(
    tmp_path: Path,
    max_duration: float = 10.0,
    min_duration: float = 0.01,
) -> EarshotApp:
    cfg = make_config(tmp_path, max_duration=max_duration, min_duration=min_duration)
    cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
    app = EarshotApp(cfg)
    with app._db_lock:
        init_schema(app._conn)
    return app


def stub_encode(
    wav_path: Path,
    opus_path: Path,
    *,
    sample_rate: int,
    bitrate_kbps: int,
    ignore_header_length: bool = False,
) -> None:
    """Fake encoder — writes an empty file without invoking ffmpeg."""
    opus_path.parent.mkdir(parents=True, exist_ok=True)
    opus_path.write_bytes(b"")


def run_session_then_stop(app: EarshotApp, button: StubButton, delay: float = 0.15) -> None:
    """Run _recording_session in a thread, stop it after *delay* seconds."""
    t = threading.Thread(target=app._recording_session)
    t.start()
    time.sleep(delay)
    button.inject_press(True)
    time.sleep(0.05)
    button.inject_press(False)
    t.join(timeout=10.0)
    assert not t.is_alive(), "Recording session did not complete within timeout"


def session_dirs(tmp_path: Path) -> list[Path]:
    return sorted((tmp_path / "recordings").glob("*/"))


# ---------------------------------------------------------------------------
# Multi-chunk session tests
# ---------------------------------------------------------------------------

class TestMultiChunkSession:
    def test_single_chunk_creates_audio_001(self, tmp_path):
        """Button press before max_duration produces audio-001.opus."""
        button = StubButton()
        app = make_app(tmp_path, max_duration=10.0)
        app._hal = make_hal(button)

        with patch("earshot.app.wav_to_opus_mono", side_effect=stub_encode):
            run_session_then_stop(app, button)

        dirs = session_dirs(tmp_path)
        assert len(dirs) == 1, "Expected exactly one session directory"
        opus_files = sorted(dirs[0].glob("audio-*.opus"))
        assert len(opus_files) == 1
        assert opus_files[0].name == "audio-001.opus"

    def test_rollover_uses_same_directory(self, tmp_path):
        """All chunks from a multi-rollover session share one session directory."""
        button = StubButton()
        app = make_app(tmp_path, max_duration=0.05)
        app._hal = make_hal(button)

        with patch("earshot.app.wav_to_opus_mono", side_effect=stub_encode):
            # 0.3 s at 0.05 s per chunk → ~6 rollovers before button press
            run_session_then_stop(app, button, delay=0.3)

        dirs = session_dirs(tmp_path)
        assert len(dirs) == 1, "All chunks must be stored in one session directory"

    def test_rollover_produces_sequential_opus_files(self, tmp_path):
        """Chunk files are numbered audio-001.opus, audio-002.opus, …"""
        button = StubButton()
        app = make_app(tmp_path, max_duration=0.05)
        app._hal = make_hal(button)

        with patch("earshot.app.wav_to_opus_mono", side_effect=stub_encode):
            run_session_then_stop(app, button, delay=0.3)

        opus_files = sorted(session_dirs(tmp_path)[0].glob("audio-*.opus"))
        assert len(opus_files) >= 2
        for i, f in enumerate(opus_files, start=1):
            assert f.name == f"audio-{i:03d}.opus", f"Unexpected filename {f.name}"

    def test_no_wav_files_remain_after_session(self, tmp_path):
        """WAV files are deleted after encoding; only opus files remain."""
        button = StubButton()
        app = make_app(tmp_path, max_duration=0.05)
        app._hal = make_hal(button)

        with patch("earshot.app.wav_to_opus_mono", side_effect=stub_encode):
            run_session_then_stop(app, button, delay=0.3)

        wav_files = list(session_dirs(tmp_path)[0].glob("recording-*.wav"))
        assert wav_files == [], f"Leftover WAV files: {wav_files}"

    def test_each_chunk_has_db_record(self, tmp_path):
        """Every opus chunk has a corresponding row in the recordings table."""
        button = StubButton()
        app = make_app(tmp_path, max_duration=0.05)
        app._hal = make_hal(button)

        with patch("earshot.app.wav_to_opus_mono", side_effect=stub_encode):
            run_session_then_stop(app, button, delay=0.3)

        opus_files = sorted(session_dirs(tmp_path)[0].glob("audio-*.opus"))
        rows = app._conn.execute(
            "SELECT audio_filename FROM recordings ORDER BY audio_filename"
        ).fetchall()
        db_names = [r[0] for r in rows]
        disk_names = [f.name for f in opus_files]
        assert db_names == disk_names, "DB records don't match files on disk"

    def test_too_short_discards_session_dir(self, tmp_path):
        """A session where every chunk is under min_duration is fully discarded."""
        button = StubButton()
        # min_duration longer than any chunk we'd record in 0.02s
        app = make_app(tmp_path, max_duration=10.0, min_duration=999.0)
        app._hal = make_hal(button)

        with patch("earshot.app.wav_to_opus_mono", side_effect=stub_encode):
            run_session_then_stop(app, button, delay=0.02)

        dirs = session_dirs(tmp_path)
        assert dirs == [], "Session directory should be removed when all chunks are too short"
        rows = app._conn.execute("SELECT COUNT(*) FROM recordings").fetchone()
        assert rows[0] == 0


# ---------------------------------------------------------------------------
# Orphaned WAV recovery tests
# ---------------------------------------------------------------------------

class TestOrphanRecovery:
    def _write_wav(self, path: Path, seconds: float = 1.0) -> None:
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * int(16000 * 2 * 2 * seconds))

    def test_numbered_wav_is_recovered(self, tmp_path):
        """recording-001.wav without audio-001.opus is re-encoded on startup."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        session_dir = cfg.storage.recordings_dir / "20260101T120000"
        session_dir.mkdir()
        wav_path = session_dir / "recording-001.wav"
        self._write_wav(wav_path)

        app = EarshotApp(cfg)
        with app._db_lock:
            init_schema(app._conn)
            with patch("earshot.app.wav_to_opus_mono", side_effect=stub_encode):
                app._recover_orphaned_wavs()

        assert not wav_path.exists(), "WAV should be deleted after successful recovery"
        assert (session_dir / "audio-001.opus").exists()
        rows = app._conn.execute("SELECT audio_filename FROM recordings").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "audio-001.opus"

    def test_multiple_orphaned_wavs_all_recovered(self, tmp_path):
        """Two orphaned chunks in one session directory are both recovered."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        session_dir = cfg.storage.recordings_dir / "20260101T130000"
        session_dir.mkdir()
        for n in (1, 2):
            self._write_wav(session_dir / f"recording-{n:03d}.wav")

        app = EarshotApp(cfg)
        with app._db_lock:
            init_schema(app._conn)
            with patch("earshot.app.wav_to_opus_mono", side_effect=stub_encode):
                app._recover_orphaned_wavs()

        for n in (1, 2):
            assert (session_dir / f"audio-{n:03d}.opus").exists()
        rows = app._conn.execute("SELECT COUNT(*) FROM recordings").fetchone()
        assert rows[0] == 2

    def test_already_encoded_chunk_is_skipped(self, tmp_path):
        """A chunk with an existing opus file is not re-encoded."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        session_dir = cfg.storage.recordings_dir / "20260101T140000"
        session_dir.mkdir()
        (session_dir / "audio-001.opus").write_bytes(b"existing")
        (session_dir / "recording-001.wav").write_bytes(b"junk")

        app = EarshotApp(cfg)
        with app._db_lock:
            init_schema(app._conn)
            encode_calls = []
            with patch("earshot.app.wav_to_opus_mono", side_effect=lambda *a, **k: encode_calls.append(1)):
                app._recover_orphaned_wavs()

        assert encode_calls == [], "Should not re-encode when opus already exists"
        assert (session_dir / "audio-001.opus").read_bytes() == b"existing"

    def test_legacy_recording_wav_recovered(self, tmp_path):
        """Legacy single-file format (recording.wav → audio.opus) still works."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        session_dir = cfg.storage.recordings_dir / "20260101T150000"
        session_dir.mkdir()
        wav_path = session_dir / "recording.wav"
        self._write_wav(wav_path)

        app = EarshotApp(cfg)
        with app._db_lock:
            init_schema(app._conn)
            with patch("earshot.app.wav_to_opus_mono", side_effect=stub_encode):
                app._recover_orphaned_wavs()

        assert not wav_path.exists()
        assert (session_dir / "audio.opus").exists()
        rows = app._conn.execute("SELECT audio_filename FROM recordings").fetchall()
        assert rows[0][0] == "audio.opus"


# ---------------------------------------------------------------------------
# DB schema migration tests
# ---------------------------------------------------------------------------

class TestDbMigration:
    def test_v2_to_v3_adds_audio_filename(self, tmp_path):
        """Migration from v2 adds audio_filename defaulting to 'audio.opus'."""
        db_path = tmp_path / "earshot.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
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
            PRAGMA user_version = 2;
        """)
        conn.execute(
            "INSERT INTO recordings VALUES (?, ?, ?, ?)",
            ("abc-123", "2026-01-01T00:00:00+00:00", "/earshot/recordings/20260101T120000", 60.0),
        )
        conn.commit()
        conn.close()

        conn2 = connect(db_path)
        init_schema(conn2)

        row = conn2.execute(
            "SELECT audio_filename FROM recordings WHERE id = 'abc-123'"
        ).fetchone()
        assert row is not None
        assert row[0] == "audio.opus", "Existing row should default to 'audio.opus'"
        conn2.close()

    def test_v3_allows_multiple_chunks_per_directory(self, tmp_path):
        """After migration, two rows can share a directory with different filenames."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        app = EarshotApp(cfg)
        with app._db_lock:
            init_schema(app._conn)

        session_dir = cfg.storage.recordings_dir / "20260101T120000"
        from earshot.storage.db import insert_recording_pending
        with app._db_lock:
            insert_recording_pending(
                app._conn,
                recorded_at="2026-01-01T12:00:00+00:00",
                directory=session_dir,
                audio_filename="audio-001.opus",
                duration_seconds=7200.0,
            )
            insert_recording_pending(
                app._conn,
                recorded_at="2026-01-01T14:00:00+00:00",
                directory=session_dir,
                audio_filename="audio-002.opus",
                duration_seconds=900.0,
            )

        rows = app._conn.execute(
            "SELECT audio_filename FROM recordings ORDER BY audio_filename"
        ).fetchall()
        assert [r[0] for r in rows] == ["audio-001.opus", "audio-002.opus"]
