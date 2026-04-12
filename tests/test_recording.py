"""Tests for multi-chunk recording session and orphaned WAV recovery."""

from __future__ import annotations

import threading
import time
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from earshot.app import EarshotApp
from earshot.config import AppConfig, AudioConfig, HardwareConfig, RecordingConfig, StorageConfig
from earshot.hal.bundle import Hal
from earshot.hal.stub import StubAudioCapture, StubButton, StubDisplay, StubLED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config(
    tmp_path: Path,
    chunk_duration: float = 10.0,
    min_duration: float = 0.01,
) -> AppConfig:
    return AppConfig(
        hardware=HardwareConfig(hat="respeaker"),
        audio=AudioConfig(
            sample_rate=16000,
            channels=2,
            bit_depth=16,
            opus_bitrate=32,
        ),
        recording=RecordingConfig(
            chunk_duration_seconds=chunk_duration,
            min_duration_seconds=min_duration,
            shutdown_hold_seconds=3.0,
        ),
        storage=StorageConfig(
            data_dir=tmp_path,
            disk_threshold_percent=90.0,
            recordings_dir=tmp_path / "recordings",
        ),
        config_path=tmp_path / "config.toml",
    )


def make_hal(button: StubButton) -> Hal:
    return Hal(
        led=StubLED(),
        button=button,
        display=StubDisplay(),
        pi_led=None,
        animator=None,
        _audio_factory=lambda: StubAudioCapture(channels=2, sample_rate=16000),
        _on_close=lambda: None,
    )


def make_app(
    tmp_path: Path,
    chunk_duration: float = 10.0,
    min_duration: float = 0.01,
) -> EarshotApp:
    cfg = make_config(tmp_path, chunk_duration=chunk_duration, min_duration=min_duration)
    cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
    return EarshotApp(cfg)


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
    def test_single_chunk_records_wav_and_creates_session_opus(self, tmp_path):
        """Button press before chunk_duration produces recording-001.wav and session.opus."""
        button = StubButton()
        app = make_app(tmp_path, chunk_duration=10.0)
        app._hal = make_hal(button)

        with patch("earshot.app.wav_to_opus_stereo", side_effect=stub_encode):
            run_session_then_stop(app, button)

        dirs = session_dirs(tmp_path)
        assert len(dirs) == 1
        # Should have recording WAV and session.opus after post-recording encode
        # (session.wav is deleted after encoding for space savings)
        assert (dirs[0] / "recording-001.wav").exists()
        assert not (dirs[0] / "session.wav").exists()
        assert (dirs[0] / "session.opus").exists()

    def test_rollover_uses_same_directory(self, tmp_path):
        """All chunks from a multi-rollover session share one session directory."""
        button = StubButton()
        app = make_app(tmp_path, chunk_duration=0.05)
        app._hal = make_hal(button)

        with patch("earshot.app.wav_to_opus_stereo", side_effect=stub_encode):
            run_session_then_stop(app, button, delay=0.3)

        dirs = session_dirs(tmp_path)
        assert len(dirs) == 1, "All chunks must be stored in one session directory"

    def test_rollover_produces_sequential_wav_files(self, tmp_path):
        """Chunk files are numbered recording-001.wav, recording-002.wav, …"""
        button = StubButton()
        app = make_app(tmp_path, chunk_duration=0.05)
        app._hal = make_hal(button)

        with patch("earshot.app.wav_to_opus_stereo", side_effect=stub_encode):
            run_session_then_stop(app, button, delay=0.3)

        wav_files = sorted(session_dirs(tmp_path)[0].glob("recording-*.wav"))
        assert len(wav_files) >= 2
        for i, f in enumerate(wav_files, start=1):
            assert f.name == f"recording-{i:03d}.wav", f"Unexpected filename {f.name}"

    def test_wav_files_kept_after_recording(self, tmp_path):
        """WAV chunk files are kept after recording for later transcription."""
        button = StubButton()
        app = make_app(tmp_path, chunk_duration=0.05)
        app._hal = make_hal(button)

        with patch("earshot.app.wav_to_opus_stereo", side_effect=stub_encode):
            run_session_then_stop(app, button, delay=0.3)

        wav_files = list(session_dirs(tmp_path)[0].glob("recording-*.wav"))
        assert len(wav_files) >= 1, "WAV files should be kept for transcription"

    def test_too_short_discards_session_dir(self, tmp_path):
        """A session where every chunk is under min_duration is fully discarded."""
        button = StubButton()
        app = make_app(tmp_path, chunk_duration=10.0, min_duration=999.0)
        app._hal = make_hal(button)

        with patch("earshot.app.wav_to_opus_stereo", side_effect=stub_encode):
            run_session_then_stop(app, button, delay=0.02)

        dirs = session_dirs(tmp_path)
        assert dirs == [], "Session directory should be removed when all chunks are too short"

    def test_concat_and_encode_on_session_complete(self, tmp_path):
        """After recording completes, WAV files are concatenated and encoded to opus."""
        button = StubButton()
        app = make_app(tmp_path, chunk_duration=0.05)
        app._hal = make_hal(button)

        with patch("earshot.app.wav_to_opus_stereo", side_effect=stub_encode):
            run_session_then_stop(app, button, delay=0.3)

        dirs = session_dirs(tmp_path)
        assert len(dirs) == 1
        session_dir = dirs[0]
        # Should have session.opus from encoding
        # (session.wav is deleted after encoding for space savings)
        assert not (session_dir / "session.wav").exists()
        assert (session_dir / "session.opus").exists()


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
        with patch("earshot.app.wav_to_opus_mono", side_effect=stub_encode):
            app._recover_orphaned_wavs()

        assert not wav_path.exists(), "WAV should be deleted after successful recovery"
        assert (session_dir / "audio-001.opus").exists()

    def test_multiple_orphaned_wavs_all_recovered(self, tmp_path):
        """Two orphaned chunks in one session directory are both recovered."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        session_dir = cfg.storage.recordings_dir / "20260101T130000"
        session_dir.mkdir()
        for n in (1, 2):
            self._write_wav(session_dir / f"recording-{n:03d}.wav")

        app = EarshotApp(cfg)
        with patch("earshot.app.wav_to_opus_mono", side_effect=stub_encode):
            app._recover_orphaned_wavs()

        for n in (1, 2):
            assert (session_dir / f"audio-{n:03d}.opus").exists()

    def test_already_encoded_chunk_is_skipped(self, tmp_path):
        """A chunk with an existing opus file is not re-encoded."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        session_dir = cfg.storage.recordings_dir / "20260101T140000"
        session_dir.mkdir()
        (session_dir / "audio-001.opus").write_bytes(b"existing")
        (session_dir / "recording-001.wav").write_bytes(b"junk")

        app = EarshotApp(cfg)
        encode_calls = []
        with patch(
            "earshot.app.wav_to_opus_mono",
            side_effect=lambda *a, **k: encode_calls.append(1),
        ):
            app._recover_orphaned_wavs()

        assert encode_calls == [], "Should not re-encode when opus already exists"
        assert (session_dir / "audio-001.opus").read_bytes() == b"existing"

    def test_failed_marker_prevents_retry(self, tmp_path):
        """A .failed_NNN marker prevents a WAV from being re-encoded on recovery."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        session_dir = cfg.storage.recordings_dir / "20260101T150000"
        session_dir.mkdir()
        (session_dir / "recording-001.wav").write_bytes(b"junk")
        (session_dir / ".failed_001").touch()

        app = EarshotApp(cfg)
        encode_calls = []
        with patch(
            "earshot.app.wav_to_opus_mono",
            side_effect=lambda *a, **k: encode_calls.append(1),
        ):
            app._recover_orphaned_wavs()

        assert encode_calls == [], "Should not retry a chunk with a .failed marker"

    def test_recovery_failure_writes_failed_marker(self, tmp_path):
        """A WAV that fails to encode during recovery gets a .failed_NNN marker."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        session_dir = cfg.storage.recordings_dir / "20260101T160000"
        session_dir.mkdir()
        self._write_wav(session_dir / "recording-001.wav")

        app = EarshotApp(cfg)
        with patch(
            "earshot.app.wav_to_opus_mono",
            side_effect=RuntimeError("ffmpeg failed"),
        ):
            app._recover_orphaned_wavs()

        assert (session_dir / ".failed_001").exists()
        assert (session_dir / "recording-001.wav").exists(), "WAV should be retained"

    def test_legacy_recording_wav_recovered(self, tmp_path):
        """Legacy single-file format (recording.wav → audio.opus) still works."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        session_dir = cfg.storage.recordings_dir / "20260101T170000"
        session_dir.mkdir()
        wav_path = session_dir / "recording.wav"
        self._write_wav(wav_path)

        app = EarshotApp(cfg)
        with patch("earshot.app.wav_to_opus_mono", side_effect=stub_encode):
            app._recover_orphaned_wavs()

        assert not wav_path.exists()
        assert (session_dir / "audio.opus").exists()
