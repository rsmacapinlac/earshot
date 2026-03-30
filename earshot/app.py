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

        # Recover any WAV files left behind by a previous crash (NFR-2).
        # Runs while the boot LED is already showing so the user gets visual feedback.
        with self._db_lock:
            self._recover_orphaned_wavs()

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

    def _recover_orphaned_wavs(self) -> None:
        """Re-encode any WAV files left behind by a previous crash (NFR-2).

        Called at startup with the db_lock already held.  Scans each session
        directory for ``recording-NNN.wav`` files (numbered chunk format) or the
        legacy ``recording.wav`` that have no corresponding opus file.  Python's
        wave module leaves zeroed chunk-size fields in the header when the process
        crashes before ``close()`` is called, so encoding uses
        ``ignore_header_length=True`` to read PCM until EOF.
        """
        import re as _re

        cfg = self._cfg
        root = recordings_root(cfg)
        if not root.exists():
            return

        bytes_per_frame = cfg.audio.channels * 2  # 16-bit = 2 bytes per sample

        for session_dir in sorted(root.iterdir()):
            if not session_dir.is_dir():
                continue

            # Collect orphaned WAVs: numbered chunks + legacy single-file format.
            numbered = sorted(session_dir.glob("recording-*.wav"))
            legacy = session_dir / "recording.wav"
            candidates: list[tuple[Path, str]] = []  # (wav_path, opus_name)
            for wav in numbered:
                m = _re.fullmatch(r"recording-(\d+)\.wav", wav.name)
                if m:
                    candidates.append((wav, f"audio-{m.group(1).zfill(3)}.opus"))
            if legacy.exists():
                candidates.append((legacy, "audio.opus"))

            for wav_path, opus_name in candidates:
                opus_path = session_dir / opus_name
                if opus_path.exists():
                    continue  # already encoded — skip

                _log.warning("Recovering orphaned WAV: %s/%s", session_dir.name, wav_path.name)

                # Measure size before encoding (we need it for duration estimation).
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
                    _log.error("Failed to recover %s/%s: %s", session_dir.name, wav_path.name, exc)
                    log_event(
                        self._conn,
                        f"WAV recovery failed for {session_dir.name}/{wav_path.name}: {exc}",
                        level="error",
                    )
                    continue

                wav_path.unlink(missing_ok=True)

                if duration_s < cfg.recording.min_duration_seconds:
                    _log.warning(
                        "Recovered chunk too short (%.1fs), discarding %s",
                        duration_s, opus_name,
                    )
                    opus_path.unlink(missing_ok=True)
                    continue

                try:
                    recorded_at = (
                        datetime.strptime(session_dir.name, "%Y%m%dT%H%M%S")
                        .astimezone()
                        .replace(microsecond=0)
                        .isoformat()
                    )
                except ValueError:
                    recorded_at = datetime.now().astimezone().replace(microsecond=0).isoformat()

                rec_id = insert_recording_pending(
                    self._conn,
                    recorded_at=recorded_at,
                    directory=session_dir,
                    audio_filename=opus_name,
                    duration_seconds=duration_s,
                )
                log_event(
                    self._conn,
                    f"Recovered {session_dir.name}/{opus_name} ({duration_s:.0f}s)",
                    level="info",
                    recording_id=rec_id,
                )
                _log.info("Recovered %s/%s (%.0fs)", session_dir.name, opus_name, duration_s)

    def _recording_session(self) -> None:
        """Capture audio until the button is pressed, rolling over to a new file each
        time ``max_duration_seconds`` is reached.

        All chunks share a single session directory named after the session start
        time.  Chunk files are numbered sequentially: ``recording-001.wav`` →
        ``audio-001.opus``, ``recording-002.wav`` → ``audio-002.opus``, etc.
        Each completed chunk is encoded in a background thread so that audio
        capture continues uninterrupted across rollovers.  The LED stays red
        throughout the session and turns blue only when waiting for the final
        encoding pass after the button is pressed.
        """
        hal = self._hal
        assert hal is not None
        cfg = self._cfg
        self._snap_recording_led(hal)

        # One directory for the whole session, named after the session start time.
        session_stamp = new_recording_stamp()
        session_dir = recording_directory(cfg, session_stamp)
        session_dir.mkdir(parents=True, exist_ok=True)

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
                recorded_at = datetime.now().astimezone().replace(microsecond=0).isoformat()

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
                    args=(session_dir, wav_path, opus_name, duration_s, recorded_at),
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

        # Clean up session directory if encoding left nothing behind.
        try:
            session_dir.rmdir()  # Only succeeds if the directory is empty.
        except OSError:
            pass  # Directory has files — expected.

        self._set_idle_led(self._disk_blocked())

    def _encode_chunk(
        self,
        session_dir: Path,
        wav_path: Path,
        opus_name: str,
        duration_s: float,
        recorded_at: str,
    ) -> None:
        """Encode one WAV chunk to Opus and register it in the database.

        Runs in a background thread so audio capture can continue into the next
        chunk without interruption.  Encoding errors are logged but do not raise
        so the thread exits cleanly.
        """
        cfg = self._cfg
        opus_path = session_dir / opus_name
        try:
            wav_to_opus_mono(
                wav_path,
                opus_path,
                sample_rate=cfg.audio.sample_rate,
                bitrate_kbps=cfg.audio.opus_bitrate,
            )
        except Exception as exc:
            _log.exception("Opus encode failed for %s/%s", session_dir.name, opus_name)
            with self._db_lock:
                log_event(
                    self._conn,
                    f"ffmpeg encode failed for {session_dir.name}/{opus_name}: {exc}",
                    level="error",
                )
            return

        wav_path.unlink(missing_ok=True)

        with self._db_lock:
            rec_id = insert_recording_pending(
                self._conn,
                recorded_at=recorded_at,
                directory=session_dir,
                audio_filename=opus_name,
                duration_seconds=duration_s,
            )
            log_event(
                self._conn,
                f"Recording saved {session_dir.name}/{opus_name}",
                level="info",
                recording_id=rec_id,
            )

    def _record_until_stop(
        self, audio, writer: StereoWavWriter, cfg: AppConfig
    ) -> tuple[int, str]:
        """Record audio frames until the button is pressed or max duration is reached.

        Returns ``(frames_recorded, reason)`` where *reason* is ``"button"`` or
        ``"max_duration"``.  The caller uses the reason to decide whether to roll
        over to a new file or end the session.
        """
        hal = self._hal
        assert hal is not None
        max_dur = cfg.recording.max_duration_seconds
        frames_recorded = 0
        prev_pressed = False
        t0 = time.monotonic()
        while True:
            pcm = audio.read_frames(_CHUNK_FRAMES)
            writer.write_frames(pcm)
            frames_recorded += _CHUNK_FRAMES
            elapsed = time.monotonic() - t0
            if elapsed >= max_dur:
                return frames_recorded, "max_duration"
            cur = hal.button.pressed()
            if cur and not prev_pressed:
                return frames_recorded, "button"
            prev_pressed = cur

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
