"""Tests for USB stick detection and recording offload (FR-11)."""

from __future__ import annotations

import errno
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from earshot.app import EarshotApp
from earshot.config import AppConfig, AudioConfig, RecordingConfig, StorageConfig
from earshot.hal.bundle import Hal
from earshot.hal.stub import StubAudioCapture, StubButton, StubLED
from earshot.usb_offload import find_usb_mount, move_recordings_to_stick


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        audio=AudioConfig(sample_rate=16000, channels=2, bit_depth=16, opus_bitrate=32),
        recording=RecordingConfig(
            chunk_duration_seconds=10.0,
            min_duration_seconds=0.01,
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
        pi_led=None,
        animator=None,
        _audio_factory=lambda: StubAudioCapture(channels=2, sample_rate=16000),
        _on_close=lambda: None,
    )


def lsblk_output(devices: list[dict]) -> str:
    return json.dumps({"blockdevices": devices})


# ---------------------------------------------------------------------------
# find_usb_mount() unit tests
# ---------------------------------------------------------------------------

class TestFindUsbMount:
    def test_returns_none_when_no_removable_device(self):
        output = lsblk_output([
            {"name": "sda", "rm": False, "fstype": None, "mountpoint": None,
             "children": [
                 {"name": "sda1", "rm": False, "fstype": "ext4",
                  "mountpoint": "/", "children": []}
             ]}
        ])
        with patch("earshot.usb_offload.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"stdout": output})()
            result = find_usb_mount()
        assert result is None

    def test_returns_none_when_removable_not_yet_mounted(self):
        """Stick present but udev hasn't finished mounting — returns None (no side-effects)."""
        output = lsblk_output([
            {"name": "sdb", "rm": True, "fstype": None, "mountpoint": None,
             "children": [
                 {"name": "sdb1", "rm": True, "fstype": "vfat",
                  "mountpoint": None, "children": []}
             ]}
        ])
        with patch("earshot.usb_offload.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"stdout": output})()
            result = find_usb_mount()
        assert result is None
        # Only lsblk should have been called — no mount attempts
        assert mock_run.call_count == 1

    def test_returns_mount_point_when_removable_vfat_mounted(self, tmp_path):
        mount = str(tmp_path / "media" / "EARSHOT")
        output = lsblk_output([
            {"name": "sdb", "rm": True, "fstype": None, "mountpoint": None,
             "children": [
                 {"name": "sdb1", "rm": True, "fstype": "vfat",
                  "mountpoint": mount, "children": []}
             ]}
        ])
        with patch("earshot.usb_offload.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"stdout": output})()
            result = find_usb_mount()
        assert result == Path(mount)

    def test_returns_none_on_lsblk_error(self):
        with patch(
            "earshot.usb_offload.subprocess.run",
            side_effect=OSError("lsblk not found"),
        ):
            result = find_usb_mount()
        assert result is None

    def test_skips_non_removable_vfat(self, tmp_path):
        """An internal vfat partition (rm=False) is not returned."""
        mount = str(tmp_path / "boot")
        output = lsblk_output([
            {"name": "mmcblk0", "rm": False, "fstype": None, "mountpoint": None,
             "children": [
                 {"name": "mmcblk0p1", "rm": False, "fstype": "vfat",
                  "mountpoint": mount, "children": []}
             ]}
        ])
        with patch("earshot.usb_offload.subprocess.run") as mock_run:
            mock_run.return_value = type("R", (), {"stdout": output})()
            result = find_usb_mount()
        assert result is None


# ---------------------------------------------------------------------------
# move_recordings_to_stick() unit tests
# ---------------------------------------------------------------------------

class TestMoveRecordingsToStick:
    def _make_session(self, root: Path, name: str, files: dict[str, bytes]) -> Path:
        session = root / name
        session.mkdir(parents=True)
        for fname, content in files.items():
            (session / fname).write_bytes(content)
        return session

    def test_moves_session_directory_to_stick(self, tmp_path):
        recordings = tmp_path / "recordings"
        stick = tmp_path / "stick"
        stick.mkdir()
        self._make_session(recordings, "20260101T120000", {"audio-001.opus": b"audio"})

        move_recordings_to_stick(recordings, stick)

        assert (stick / "20260101T120000" / "audio-001.opus").read_bytes() == b"audio"
        assert not (recordings / "20260101T120000").exists()

    def test_moves_multiple_sessions(self, tmp_path):
        recordings = tmp_path / "recordings"
        stick = tmp_path / "stick"
        stick.mkdir()
        for name in ("20260101T120000", "20260101T130000"):
            self._make_session(recordings, name, {"audio-001.opus": b"data"})

        move_recordings_to_stick(recordings, stick)

        assert (stick / "20260101T120000").exists()
        assert (stick / "20260101T130000").exists()
        assert list(recordings.glob("*/")) == []

    def test_moves_partial_session_with_failed_markers(self, tmp_path):
        """Sessions with .failed markers are moved as-is."""
        recordings = tmp_path / "recordings"
        stick = tmp_path / "stick"
        stick.mkdir()
        self._make_session(
            recordings,
            "20260101T120000",
            {"audio-001.opus": b"ok", "recording-002.wav": b"raw", ".failed_002": b""},
        )

        move_recordings_to_stick(recordings, stick)

        dest = stick / "20260101T120000"
        assert (dest / "audio-001.opus").exists()
        assert (dest / "recording-002.wav").exists()
        assert (dest / ".failed_002").exists()

    def test_raises_enospc_when_stick_is_full(self, tmp_path):
        recordings = tmp_path / "recordings"
        stick = tmp_path / "stick"
        stick.mkdir()
        self._make_session(recordings, "20260101T120000", {"audio-001.opus": b"data"})

        enospc = OSError(errno.ENOSPC, "No space left on device")
        with patch("earshot.usb_offload.shutil.copy2", side_effect=enospc):
            with pytest.raises(OSError) as exc_info:
                move_recordings_to_stick(recordings, stick)
        assert exc_info.value.errno == errno.ENOSPC

    def test_noop_when_recordings_root_does_not_exist(self, tmp_path):
        stick = tmp_path / "stick"
        stick.mkdir()
        move_recordings_to_stick(tmp_path / "nonexistent", stick)  # should not raise


# ---------------------------------------------------------------------------
# App-level USB offload integration tests
# ---------------------------------------------------------------------------

class TestAppUsbOffload:
    def test_usb_offload_moves_sessions_and_signals_complete(self, tmp_path):
        """_usb_offload moves recordings to the stick and resets to idle."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        session = cfg.storage.recordings_dir / "20260101T120000"
        session.mkdir()
        (session / "audio-001.opus").write_bytes(b"audio")

        stick = tmp_path / "stick"
        stick.mkdir()

        app = EarshotApp(cfg)
        app._hal = make_hal(StubButton())
        app._usb_stick_pending.set()

        with patch("earshot.app.find_usb_device", return_value=("/dev/sda1", str(stick))), \
             patch("earshot.app.eject_usb_device"), \
             patch("earshot.app.flash_single_blue"):
            app._usb_offload()

        assert (stick / "20260101T120000" / "audio-001.opus").exists()
        assert not session.exists()
        assert not app._usb_error.is_set()
        assert not app._usb_stick_pending.is_set()

    def test_usb_offload_sets_error_on_enospc(self, tmp_path):
        """_usb_offload sets _usb_error and shows orange LED when stick is full."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        session = cfg.storage.recordings_dir / "20260101T120000"
        session.mkdir()
        (session / "audio-001.opus").write_bytes(b"audio")

        stick = tmp_path / "stick"
        stick.mkdir()

        app = EarshotApp(cfg)
        app._hal = make_hal(StubButton())
        app._usb_stick_pending.set()

        enospc = OSError(errno.ENOSPC, "No space left")
        with patch("earshot.app.find_usb_device", return_value=("/dev/sda1", str(stick))), \
             patch("earshot.app.move_recordings_to_stick", side_effect=enospc):
            app._usb_offload()

        assert app._usb_error.is_set()

    def test_usb_offload_skips_when_not_mounted(self, tmp_path):
        """_usb_offload clears pending and skips if stick is present but not yet mounted."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        app = EarshotApp(cfg)
        app._hal = make_hal(StubButton())
        app._usb_stick_pending.set()

        with patch("earshot.app.find_usb_device", return_value=("/dev/sda1", None)):
            app._usb_offload()

        assert not app._usb_stick_pending.is_set()
        assert not app._usb_error.is_set()

    def _run_monitor_iterations(self, app: EarshotApp, mock_find, iterations: int) -> None:
        """Run the USB monitor loop for a fixed number of find() calls, then stop."""
        count = [0]
        original_find = mock_find

        def counting_find():
            result = original_find()
            count[0] += 1
            if count[0] >= iterations:
                app._usb_stop.set()
            return result

        def instant_wait(timeout: float) -> bool:
            time.sleep(0.01)
            return app._usb_stop.is_set()

        t = threading.Thread(target=app._usb_monitor_loop, daemon=True)
        with patch("earshot.app.find_usb_device", side_effect=counting_find), \
             patch.object(app._usb_stop, "wait", side_effect=instant_wait):
            t.start()
            t.join(timeout=3.0)

    def test_usb_monitor_sets_pending_on_insert(self, tmp_path):
        """_usb_monitor_loop sets _usb_stick_pending when a stick appears."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        app = EarshotApp(cfg)
        app._hal = make_hal(StubButton())

        call_count = [0]

        def mock_find():
            call_count[0] += 1
            return ("/dev/sda1", None) if call_count[0] >= 2 else None

        self._run_monitor_iterations(app, mock_find, iterations=3)

        assert app._usb_stick_pending.is_set()

    def test_usb_monitor_clears_pending_on_remove(self, tmp_path):
        """_usb_monitor_loop clears _usb_stick_pending when stick is removed."""
        cfg = make_config(tmp_path)
        cfg.storage.recordings_dir.mkdir(parents=True, exist_ok=True)
        app = EarshotApp(cfg)
        app._hal = make_hal(StubButton())
        app._usb_stick_pending.set()  # already set

        call_count = [0]

        def mock_find():
            call_count[0] += 1
            # First call: stick present; second: gone
            return ("/dev/sda1", None) if call_count[0] == 1 else None

        self._run_monitor_iterations(app, mock_find, iterations=3)

        assert not app._usb_stick_pending.is_set()
        assert not app._usb_error.is_set()
