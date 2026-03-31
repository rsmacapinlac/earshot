"""Tests for connectivity detection and sync gating (FR-9)."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from earshot.app import EarshotApp
from earshot.config import ApiConfig, AppConfig, AudioConfig, RecordingConfig, StorageConfig
from earshot.hal.bundle import Hal
from earshot.hal.stub import StubAudioCapture, StubButton, StubLED
from earshot.storage.db import init_schema
from earshot.sync.client import check_connectivity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config(tmp_path: Path, sync_interval: float = 0.05) -> AppConfig:
    return AppConfig(
        audio=AudioConfig(
            sample_rate=16000,
            channels=2,
            bit_depth=16,
            opus_bitrate=32,
        ),
        recording=RecordingConfig(
            max_duration_seconds=10.0,
            min_duration_seconds=0.01,
            shutdown_hold_seconds=3.0,
        ),
        storage=StorageConfig(
            data_dir=tmp_path,
            disk_threshold_percent=90.0,
            recordings_dir=tmp_path / "recordings",
        ),
        api=ApiConfig(
            endpoint="https://api.example.com",
            secret=None,
            sync_interval_seconds=sync_interval,
        ),
        config_path=tmp_path / "config.toml",
    )


def make_app(tmp_path: Path, sync_interval: float = 0.05) -> EarshotApp:
    cfg = make_config(tmp_path, sync_interval=sync_interval)
    cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
    app = EarshotApp(cfg)
    with app._db_lock:
        init_schema(app._conn)
    return app


def make_hal(button: StubButton) -> Hal:
    return Hal(
        led=StubLED(),
        button=button,
        pi_led=None,
        animator=None,
        _audio_factory=lambda: StubAudioCapture(channels=2, sample_rate=16000),
        _on_close=lambda: None,
    )


def stub_encode(wav_path, opus_path, *, sample_rate, bitrate_kbps, ignore_header_length=False):
    opus_path.parent.mkdir(parents=True, exist_ok=True)
    opus_path.write_bytes(b"")


# ---------------------------------------------------------------------------
# check_connectivity() unit tests
# ---------------------------------------------------------------------------

class TestCheckConnectivity:
    def test_returns_true_when_socket_connects(self):
        mock_sock = MagicMock()
        mock_sock.__enter__ = lambda s: s
        mock_sock.__exit__ = MagicMock(return_value=False)
        with patch("earshot.sync.client.socket.create_connection", return_value=mock_sock):
            assert check_connectivity() is True

    def test_returns_false_on_os_error(self):
        with patch("earshot.sync.client.socket.create_connection", side_effect=OSError):
            assert check_connectivity() is False

    def test_returns_false_on_timeout(self):
        with patch("earshot.sync.client.socket.create_connection", side_effect=TimeoutError):
            assert check_connectivity() is False


# ---------------------------------------------------------------------------
# Idle event management
# ---------------------------------------------------------------------------

class TestIdleEvent:
    def test_event_cleared_during_recording_and_restored_after(self, tmp_path):
        """_idle_event is cleared when recording starts and set when it ends."""
        button = StubButton()
        app = make_app(tmp_path)
        app._hal = make_hal(button)
        app._idle_event.set()

        t = threading.Thread(target=app._recording_session)
        with patch("earshot.app.wav_to_opus_mono", side_effect=stub_encode):
            t.start()
            time.sleep(0.05)  # let recording start
            assert not app._idle_event.is_set(), "Event should be cleared while recording"
            button.inject_press(True)
            time.sleep(0.05)
            button.inject_press(False)
            t.join(timeout=5.0)

        assert not t.is_alive(), "Recording session did not complete"
        assert app._idle_event.is_set(), "Event should be restored after recording"

    def test_event_restored_after_audio_start_failure(self, tmp_path):
        """_idle_event is set even when audio capture fails to start."""
        app = make_app(tmp_path)
        app._idle_event.set()

        broken_audio = MagicMock()
        broken_audio.start.side_effect = RuntimeError("device not found")
        app._hal = Hal(
            led=StubLED(),
            button=StubButton(),
            pi_led=None,
            animator=None,
            _audio_factory=lambda: broken_audio,
            _on_close=lambda: None,
        )

        app._recording_session()

        assert app._idle_event.is_set(), "Event should be restored even after audio failure"


# ---------------------------------------------------------------------------
# Sync loop gating
# ---------------------------------------------------------------------------

class TestSyncLoopGating:
    def _run_sync_loop_briefly(self, app: EarshotApp, duration: float = 0.3) -> None:
        t = threading.Thread(target=app._sync_loop, daemon=True)
        t.start()
        time.sleep(duration)
        app._sync_stop.set()
        t.join(timeout=2.0)

    def test_sync_skipped_when_not_idle(self, tmp_path):
        """sync_pending_uploads is not called when the device is not idle."""
        app = make_app(tmp_path)
        # _idle_event intentionally left unset

        with patch("earshot.app.check_connectivity", return_value=True), \
             patch("earshot.app.sync_pending_uploads") as mock_sync:
            self._run_sync_loop_briefly(app)

        mock_sync.assert_not_called()

    def test_sync_skipped_when_no_connectivity(self, tmp_path):
        """sync_pending_uploads is not called when offline."""
        app = make_app(tmp_path)
        app._idle_event.set()

        with patch("earshot.app.check_connectivity", return_value=False), \
             patch("earshot.app.sync_pending_uploads") as mock_sync:
            self._run_sync_loop_briefly(app)

        mock_sync.assert_not_called()

    def test_sync_runs_when_idle_and_connected(self, tmp_path):
        """sync_pending_uploads is called when idle and connected."""
        app = make_app(tmp_path)
        app._idle_event.set()

        with patch("earshot.app.check_connectivity", return_value=True), \
             patch("earshot.app.sync_pending_uploads") as mock_sync:
            self._run_sync_loop_briefly(app)

        assert mock_sync.call_count >= 1

    def test_connectivity_restored_logged(self, tmp_path, caplog):
        """An info log is emitted when connectivity transitions from offline to online."""
        app = make_app(tmp_path, sync_interval=0.05)
        app._idle_event.set()

        # First call returns offline, subsequent calls return online
        responses = iter([False, True, True, True, True, True])

        with patch("earshot.app.check_connectivity", side_effect=lambda: next(responses, True)), \
             patch("earshot.app.sync_pending_uploads"), \
             caplog.at_level(logging.INFO, logger="earshot.app"):
            self._run_sync_loop_briefly(app, duration=0.4)

        assert "connectivity restored" in caplog.text.lower()


# ---------------------------------------------------------------------------
# ApiConfig.sync_interval_seconds default
# ---------------------------------------------------------------------------

class TestApiConfigDefault:
    def test_sync_interval_defaults_to_30(self):
        cfg = ApiConfig(endpoint="", secret=None)
        assert cfg.sync_interval_seconds == 30.0

    def test_sync_interval_is_configurable(self):
        cfg = ApiConfig(endpoint="", secret=None, sync_interval_seconds=60.0)
        assert cfg.sync_interval_seconds == 60.0
