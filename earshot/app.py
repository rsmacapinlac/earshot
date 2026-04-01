"""Application state machine: boot, idle, record, encode, USB offload, shutdown."""

from __future__ import annotations

import errno
import logging
import re as _re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from earshot.config import AppConfig
from earshot.hal import Hal, LedPattern, create_hal
from earshot.hal.effects import flash_double_green, flash_fast_red_three_times, flash_single_blue
from earshot.recording import StereoWavWriter, wav_to_opus_mono
from earshot.storage import (
    is_over_disk_threshold,
    new_recording_stamp,
    recording_directory,
    recordings_root,
)
from earshot.usb_offload import find_usb_device, find_usb_mount, move_recordings_to_stick, unmount_usb_stick

_log = logging.getLogger(__name__)

_CHUNK_FRAMES = 1024


class EarshotApp:
    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._hal: Hal | None = None
        self._usb_stick_pending = threading.Event()
        self._usb_error = threading.Event()
        self._usb_stop = threading.Event()
        self._encode_failure = threading.Event()

    def run(self) -> None:
        cfg = self._cfg
        recordings_root(cfg).mkdir(parents=True, exist_ok=True)

        self._hal = create_hal(cfg)
        hal = self._hal

        hal.led.set_colour_and_pattern(255, 255, 255, LedPattern.SLOW_PULSE)

        # Recover any WAV files left behind by a previous crash (NFR-2).
        self._recover_orphaned_wavs()

        disk_blocked = self._disk_blocked()
        if disk_blocked:
            hal.led.set_colour_and_pattern(255, 128, 0, LedPattern.SLOW_PULSE)
            _log.warning("Disk threshold reached at startup")

        self._set_idle_led(disk_blocked)

        usb_thread = threading.Thread(
            target=self._usb_monitor_loop,
            name="earshot-usb",
            daemon=True,
        )
        usb_thread.start()

        try:
            self._main_loop()
        finally:
            self._usb_stop.set()
            usb_thread.join(timeout=5.0)
            hal.close()

    def _disk_blocked(self) -> bool:
        return is_over_disk_threshold(
            recordings_root(self._cfg),
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

            # USB stick inserted while idle → offload immediately.
            if self._usb_stick_pending.is_set() and not self._usb_error.is_set():
                self._usb_offload()
                continue

            self._set_idle_led(False)
            _log.info("Ready: green = idle, orange = disk full, press button to record.")

            action = self._wait_idle_button()
            if action == "shutdown":
                self._shutdown_sequence()
                return
            if action != "click":
                continue

            if self._disk_blocked():
                continue

            self._recording_session()

            # USB stick was inserted during recording → offload now that session is done.
            if self._usb_stick_pending.is_set() and not self._usb_error.is_set():
                self._usb_offload()

    def _wait_idle_button(self) -> str:
        """Wait for a debounced short click (record) or long hold (shutdown)."""
        hal = self._hal
        assert hal is not None
        hold = self._cfg.recording.shutdown_hold_seconds
        min_click_s = 0.03
        poll_s = 0.02
        heartbeat_deadline = time.monotonic() + 45.0

        while True:
            # Wait for a stable released state.
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

            # Wait for a stable press.
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

    def _recover_orphaned_wavs(self) -> None:
        """Re-encode WAV files left behind by a previous crash (NFR-2).

        Scans each session directory for ``recording-NNN.wav`` files that have
        no corresponding opus file and no ``.failed_NNN`` marker.  Uses
        ``ignore_header_length=True`` to handle WAVs with zeroed chunk-size
        fields written by a crash before ``close()`` was called.
        """
        cfg = self._cfg
        root = recordings_root(cfg)
        if not root.exists():
            return

        bytes_per_frame = cfg.audio.channels * 2  # 16-bit = 2 bytes per sample

        for session_dir in sorted(root.iterdir()):
            if not session_dir.is_dir():
                continue

            numbered = sorted(session_dir.glob("recording-*.wav"))
            legacy = session_dir / "recording.wav"
            candidates: list[tuple[Path, str, str]] = []
            for wav in numbered:
                m = _re.fullmatch(r"recording-(\d+)\.wav", wav.name)
                if m:
                    n = m.group(1).zfill(3)
                    candidates.append((wav, f"audio-{n}.opus", f".failed_{n}"))
            if legacy.exists():
                candidates.append((legacy, "audio.opus", ".failed"))

            for wav_path, opus_name, failed_name in candidates:
                opus_path = session_dir / opus_name
                failed_path = session_dir / failed_name
                if opus_path.exists() or failed_path.exists():
                    continue  # already encoded or previously failed — skip

                _log.warning(
                    "Recovering orphaned WAV: %s/%s", session_dir.name, wav_path.name
                )

                wav_bytes = wav_path.stat().st_size
                duration_s = max(0, wav_bytes - 44) / (bytes_per_frame * cfg.audio.sample_rate)

                try:
                    wav_to_opus_mono(
                        wav_path,
                        opus_path,
                        sample_rate=cfg.audio.sample_rate,
                        bitrate_kbps=cfg.audio.opus_bitrate,
                        ignore_header_length=True,
                    )
                except Exception as exc:
                    _log.error(
                        "Recovery failed for %s/%s: %s",
                        session_dir.name,
                        wav_path.name,
                        exc,
                    )
                    failed_path.touch()
                    continue

                wav_path.unlink(missing_ok=True)

                if duration_s < cfg.recording.min_duration_seconds:
                    _log.warning(
                        "Recovered chunk too short (%.1fs), discarding %s",
                        duration_s,
                        opus_name,
                    )
                    opus_path.unlink(missing_ok=True)
                else:
                    _log.info(
                        "Recovered %s/%s (%.0fs)", session_dir.name, opus_name, duration_s
                    )

    def _recording_session(self) -> None:
        """Capture audio until the button is pressed, rolling over every
        ``chunk_duration_seconds``.

        All chunks share one session directory named after the session start
        time.  Chunk files are numbered sequentially: ``recording-001.wav`` →
        ``audio-001.opus``, etc.  Each completed chunk is encoded in a
        background thread so capture continues uninterrupted across rollovers.
        The LED stays red throughout and turns blue only while waiting for the
        final encoding pass after the button is pressed.
        """
        hal = self._hal
        assert hal is not None
        cfg = self._cfg
        self._encode_failure.clear()
        self._snap_recording_led(hal)

        session_stamp = new_recording_stamp()
        session_dir = recording_directory(cfg, session_stamp)
        session_dir.mkdir(parents=True, exist_ok=True)

        try:
            audio = hal.new_audio_capture()
            try:
                audio.start()
            except Exception:
                _log.exception("audio capture start failed")
                audio.close()
                shutil.rmtree(session_dir, ignore_errors=True)
                self._set_idle_led(self._disk_blocked())
                return

            encode_threads: list[threading.Thread] = []
            session_too_short = False
            chunk_num = 0

            try:
                while True:
                    chunk_num += 1
                    wav_name = f"recording-{chunk_num:03d}.wav"
                    opus_name = f"audio-{chunk_num:03d}.opus"
                    wav_path = session_dir / wav_name

                    writer: StereoWavWriter | None = None
                    try:
                        writer = StereoWavWriter(
                            wav_path,
                            sample_rate=cfg.audio.sample_rate,
                            channels=cfg.audio.channels,
                        )
                        frames_recorded, reason = self._record_until_stop(audio, writer, cfg)
                    except Exception:
                        _log.exception("recording failed")
                        if writer is not None:
                            try:
                                writer.close()
                            except OSError:
                                pass
                        wav_path.unlink(missing_ok=True)
                        break

                    writer.close()

                    duration_s = frames_recorded / float(cfg.audio.sample_rate)
                    if duration_s < cfg.recording.min_duration_seconds:
                        wav_path.unlink(missing_ok=True)
                        if reason == "button" and not encode_threads:
                            session_too_short = True
                        if reason == "button":
                            break
                        continue

                    t = threading.Thread(
                        target=self._encode_chunk,
                        args=(session_dir, wav_path, opus_name),
                        name=f"earshot-encode-{session_stamp}-{chunk_num:03d}",
                        daemon=True,
                    )
                    t.start()
                    encode_threads.append(t)

                    if reason == "button":
                        break
                    _log.info("Rolling over to chunk %d after %.0fs", chunk_num + 1, duration_s)

            finally:
                try:
                    audio.stop()
                except Exception:
                    pass
                audio.close()

            if not encode_threads and session_too_short:
                shutil.rmtree(session_dir, ignore_errors=True)
                flash_double_green(hal)
                self._set_idle_led(self._disk_blocked())
                return

            if encode_threads:
                hal.led.set_colour_and_pattern(0, 0, 255, LedPattern.SLOW_PULSE)
                for t in encode_threads:
                    t.join()

            if self._encode_failure.is_set():
                flash_fast_red_three_times(hal)

            # Remove session dir if encoding left nothing behind.
            try:
                session_dir.rmdir()
            except OSError:
                pass

            self._set_idle_led(self._disk_blocked())

        except Exception:
            _log.exception("unexpected error in recording session")
            self._set_idle_led(self._disk_blocked())

    def _encode_chunk(
        self,
        session_dir: Path,
        wav_path: Path,
        opus_name: str,
    ) -> None:
        """Encode one WAV chunk to Opus in a background thread.

        On success: WAV is deleted.
        On failure: ``.failed_NNN`` marker is written, WAV is retained,
        and the session-level failure flag is set so the LED can flash after
        all chunks are joined.
        """
        cfg = self._cfg
        opus_path = session_dir / opus_name
        # audio-001.opus → .failed_001; legacy audio.opus → .failed
        chunk_num = opus_name[len("audio-"):-len(".opus")]
        failed_name = f".failed_{chunk_num}" if chunk_num.isdigit() else ".failed"
        failed_path = session_dir / failed_name

        try:
            wav_to_opus_mono(
                wav_path,
                opus_path,
                sample_rate=cfg.audio.sample_rate,
                bitrate_kbps=cfg.audio.opus_bitrate,
            )
        except Exception as exc:
            _log.error(
                "Opus encode failed for %s/%s: %s", session_dir.name, opus_name, exc
            )
            failed_path.touch()
            self._encode_failure.set()
            return

        wav_path.unlink(missing_ok=True)
        _log.info("Encoded %s/%s", session_dir.name, opus_name)

    def _record_until_stop(
        self, audio, writer: StereoWavWriter, cfg: AppConfig
    ) -> tuple[int, str]:
        """Record frames until the button is pressed or the chunk duration is reached.

        Returns ``(frames_recorded, reason)`` where *reason* is ``"button"``
        (end session) or ``"max_duration"`` (roll over to next chunk).
        """
        hal = self._hal
        assert hal is not None
        chunk_dur = cfg.recording.chunk_duration_seconds
        frames_recorded = 0
        prev_pressed = False
        t0 = time.monotonic()
        while True:
            pcm = audio.read_frames(_CHUNK_FRAMES)
            writer.write_frames(pcm)
            frames_recorded += _CHUNK_FRAMES
            elapsed = time.monotonic() - t0
            if elapsed >= chunk_dur:
                return frames_recorded, "max_duration"
            cur = hal.button.pressed()
            if cur and not prev_pressed:
                return frames_recorded, "button"
            prev_pressed = cur

    # ── USB stick offload (FR-11) ────────────────────────────────────────────

    def _usb_monitor_loop(self) -> None:
        """Poll every 2 s for removable FAT32 stick insertion/removal."""
        was_present = False
        while not self._usb_stop.wait(2.0):
            now_present = find_usb_device() is not None
            if now_present and not was_present:
                _log.info("USB stick detected")
                self._usb_error.clear()
                self._usb_stick_pending.set()
            elif not now_present and was_present:
                _log.info("USB stick removed — error state cleared")
                self._usb_stick_pending.clear()
                self._usb_error.clear()
            was_present = now_present

    def _usb_offload(self) -> None:
        """Move all session directories to the USB stick (FR-11).

        LED is blue-pulsing during transfer.  On success: single blue flash,
        then return to idle green.  On stick-full or other error: orange
        pulse until the stick is removed.
        """
        hal = self._hal
        assert hal is not None

        hal.led.set_colour_and_pattern(0, 0, 255, LedPattern.SLOW_PULSE)

        mount = find_usb_mount()
        if mount is None:
            _log.warning("USB stick no longer available — skipping offload")
            self._usb_stick_pending.clear()
            self._set_idle_led(self._disk_blocked())
            return

        try:
            move_recordings_to_stick(recordings_root(self._cfg), mount)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                _log.error("USB stick full — some recordings remain on device")
            else:
                _log.error("USB offload error: %s", exc)
            self._usb_error.set()
            hal.led.set_colour_and_pattern(255, 128, 0, LedPattern.SLOW_PULSE)
            return

        try:
            subprocess.run(["sync"], check=False, timeout=10.0)
        except Exception:
            pass

        unmount_usb_stick()
        _log.info("USB offload complete")
        flash_single_blue(hal)
        self._set_idle_led(self._disk_blocked())

    # ── Shutdown ─────────────────────────────────────────────────────────────

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
