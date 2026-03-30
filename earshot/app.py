"""Application state machine: boot, idle, record, encode, sync, shutdown."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from earshot.config import AppConfig
from earshot.hal import Hal, LedPattern, create_hal
from earshot.hal.effects import flash_double_green, flash_fast_red_three_times
from earshot.recording import StereoWavWriter, wav_to_opus_mono
from earshot.storage import (
    connect,
    database_path,
    init_schema,
    insert_recording_pending,
    is_over_disk_threshold,
    log_event,
    new_recording_stamp,
    recording_directory,
    recordings_root,
)
from earshot.sync import sync_pending_uploads

_log = logging.getLogger(__name__)

_CHUNK_FRAMES = 1024
_SYNC_INTERVAL_S = 30.0


class EarshotApp:
    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._conn = connect(database_path(cfg))
        self._db_lock = threading.Lock()
        self._hal: Hal | None = None
        self._sync_stop = threading.Event()

    def run(self) -> None:
        cfg = self._cfg
        self._ensure_directories()
        with self._db_lock:
            init_schema(self._conn)
            log_event(self._conn, "Earshot starting", level="info")

        self._hal = create_hal(cfg)
        hal = self._hal
        assert hal is not None

        hal.led.set_colour_and_pattern(255, 255, 255, LedPattern.SLOW_PULSE)

        disk_blocked = self._disk_blocked()
        if disk_blocked:
            hal.led.set_colour_and_pattern(255, 128, 0, LedPattern.SLOW_PULSE)
            log_event(self._conn, "Disk threshold reached at startup", level="warning")

        self._set_idle_led(disk_blocked)

        sync_thread = threading.Thread(
            target=self._sync_loop,
            name="earshot-sync",
            daemon=True,
        )
        sync_thread.start()

        try:
            self._main_loop()
        finally:
            self._sync_stop.set()
            sync_thread.join(timeout=5.0)
            hal.close()
            with self._db_lock:
                self._conn.close()

    def _ensure_directories(self) -> None:
        recordings_root(self._cfg).mkdir(parents=True, exist_ok=True)
        self._cfg.storage.data_dir.mkdir(parents=True, exist_ok=True)

    def _disk_blocked(self) -> bool:
        return is_over_disk_threshold(
            self._cfg.storage.data_dir,
            self._cfg.storage.disk_threshold_percent,
        )

    def _set_idle_led(self, disk_blocked: bool) -> None:
        hal = self._hal
        assert hal is not None
        if disk_blocked:
            hal.led.set_colour_and_pattern(255, 128, 0, LedPattern.SLOW_PULSE)
        else:
            hal.led.set_colour_and_pattern(0, 255, 0, LedPattern.SOLID)

    def _main_loop(self) -> None:
        hal = self._hal
        assert hal is not None
        while True:
            while self._disk_blocked():
                hal.led.set_colour_and_pattern(255, 128, 0, LedPattern.SLOW_PULSE)
                time.sleep(0.5)

            self._set_idle_led(False)
            _log.info("Ready: solid green = idle; orange pulse = disk full; press button to record.")

            action = self._wait_idle_button()
            if action == "shutdown":
                self._shutdown_sequence()
                return
            if action != "click":
                continue

            if self._disk_blocked():
                continue

            self._recording_session()

    def _wait_idle_button(self) -> str:
        """Wait for a debounced short click (record) or long hold (shutdown)."""
        hal = self._hal
        assert hal is not None
        hold = self._cfg.recording.shutdown_hold_seconds
        min_click_s = 0.03
        poll_s = 0.02
        heartbeat_deadline = time.monotonic() + 45.0

        while True:
            # Wait for a stable *released* state (avoids interpreting bounce as a release).
            while True:
                if not hal.button.pressed():
                    time.sleep(poll_s)
                    if not hal.button.pressed():
                        break
                else:
                    now = time.monotonic()
                    if now >= heartbeat_deadline:
                        _log.info(
                            "Still waiting for button (GPIO17, active-low). "
                            "If the LED never reacts, check HAT seating, wiring, and "
                            "that the earshot service has the gpio supplementary group."
                        )
                        heartbeat_deadline = now + 120.0
                time.sleep(poll_s)

            # Wait for a stable *press*.
            while not hal.button.pressed():
                time.sleep(poll_s)
            time.sleep(poll_s)
            if not hal.button.pressed():
                continue

            t_down = time.monotonic()
            while hal.button.pressed():
                if time.monotonic() - t_down >= hold:
                    _log.info("Button held %.0fs — safe shutdown", hold)
                    return "shutdown"
                time.sleep(poll_s)

            held = time.monotonic() - t_down
            if held < min_click_s:
                _log.debug("Ignoring very short button edge (%.0f ms)", held * 1000)
                continue
            if held >= hold:
                return "shutdown"
            _log.info("Button: starting recording (press lasted %.2fs)", held)
            return "click"

    def _snap_recording_led(self, hal: Hal) -> None:
        """Solid red on hardware immediately; then slow pulse via the LED facade."""
        if hal.pi_led is not None:
            hal.pi_led.set_target_rgb(255, 0, 0)
            hal.pi_led.render_scaled(1.0)
        hal.led.set_colour_and_pattern(255, 0, 0, LedPattern.SLOW_PULSE)

    def _recording_session(self) -> None:
        hal = self._hal
        assert hal is not None
        cfg = self._cfg
        self._snap_recording_led(hal)

        stamp = new_recording_stamp()
        rec_dir = recording_directory(cfg, stamp)
        rec_dir.mkdir(parents=True, exist_ok=True)
        wav_path = rec_dir / "recording.wav"
        recorded_at = datetime.now().astimezone().replace(microsecond=0).isoformat()

        audio = hal.new_audio_capture()
        writer: StereoWavWriter | None = None
        frames_recorded = 0
        try:
            audio.start()
            writer = StereoWavWriter(
                wav_path,
                sample_rate=cfg.audio.sample_rate,
                channels=cfg.audio.channels,
            )
            frames_recorded = self._record_until_stop(audio, writer, cfg)
        except Exception:
            _log.exception("recording failed")
            if writer is not None:
                try:
                    writer.close()
                except OSError:
                    pass
            try:
                audio.stop()
            except Exception:
                pass
            audio.close()
            shutil.rmtree(rec_dir, ignore_errors=True)
            hal.led.set_colour_and_pattern(0, 255, 0, LedPattern.SOLID)
            return

        try:
            audio.stop()
        except Exception:
            pass
        audio.close()
        writer.close()

        duration_s = frames_recorded / float(cfg.audio.sample_rate)
        if duration_s < cfg.recording.min_duration_seconds:
            shutil.rmtree(rec_dir, ignore_errors=True)
            flash_double_green(hal)
            self._set_idle_led(self._disk_blocked())
            return

        hal.led.set_colour_and_pattern(0, 0, 255, LedPattern.SLOW_PULSE)

        opus_path = rec_dir / "audio.opus"
        try:
            wav_to_opus_mono(
                wav_path,
                opus_path,
                sample_rate=cfg.audio.sample_rate,
                bitrate_kbps=cfg.audio.opus_bitrate,
            )
        except Exception as exc:
            _log.exception("Opus encode failed")
            with self._db_lock:
                log_event(self._conn, f"ffmpeg encode failed: {exc}", level="error")
            flash_fast_red_three_times(hal)
            self._set_idle_led(self._disk_blocked())
            return

        wav_path.unlink(missing_ok=True)

        with self._db_lock:
            rec_id = insert_recording_pending(
                self._conn,
                recorded_at=recorded_at,
                directory=rec_dir,
                duration_seconds=duration_s,
            )
            log_event(
                self._conn,
                f"Recording saved {stamp}",
                level="info",
                recording_id=rec_id,
            )

        self._set_idle_led(self._disk_blocked())

    def _record_until_stop(self, audio, writer: StereoWavWriter, cfg: AppConfig) -> int:
        hal = self._hal
        assert hal is not None
        max_dur = cfg.recording.max_duration_seconds
        rate = cfg.audio.sample_rate
        frames_recorded = 0
        prev_pressed = False
        t0 = time.monotonic()
        while True:
            pcm = audio.read_frames(_CHUNK_FRAMES)
            writer.write_frames(pcm)
            frames_recorded += _CHUNK_FRAMES
            elapsed = time.monotonic() - t0
            if elapsed >= max_dur:
                break
            cur = hal.button.pressed()
            if cur and not prev_pressed:
                break
            prev_pressed = cur
        return frames_recorded

    def _shutdown_sequence(self) -> None:
        hal = self._hal
        assert hal is not None
        hal.led.set_colour_and_pattern(255, 255, 255, LedPattern.SLOW_PULSE)
        time.sleep(1.0)
        if hal.animator is not None:
            hal.animator.run_fade_off(2.0)
        _log.info("requesting system poweroff")
        subprocess.run(
            ["/usr/bin/sudo", "-n", "/sbin/poweroff"],
            check=False,
        )

    def _sync_loop(self) -> None:
        while not self._sync_stop.wait(_SYNC_INTERVAL_S):
            try:
                with self._db_lock:
                    sync_pending_uploads(
                        self._conn,
                        self._cfg.api.endpoint,
                        self._cfg.api.secret,
                    )
            except Exception:
                _log.exception("sync batch failed")
