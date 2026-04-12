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

from faster_whisper import WhisperModel

from earshot.config import AppConfig
from earshot.hal import Hal, LedPattern, create_hal
from earshot.hal.effects import flash_double_green, flash_fast_red_three_times, flash_single_blue
from earshot.recording import StereoWavWriter, concat_wav_files, wav_to_opus_mono, wav_to_opus_stereo
from earshot.status import Status, load_status, save_status
from earshot.storage import (
    disk_usage_percent,
    is_over_disk_threshold,
    new_recording_stamp,
    recording_directory,
    recordings_root,
)
from earshot.transcription import pending_sessions, transcribe_session, write_transcript
from earshot.usb_offload import (
    GadgetOffload,
    eject_usb_device,
    find_usb_device,
    find_usb_mount,
    move_recordings_to_stick,
)

_log = logging.getLogger(__name__)

_CHUNK_FRAMES = 1024


class EarshotApp:
    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._hal: Hal | None = None
        self._usb_stick_pending = threading.Event()
        self._usb_error = threading.Event()
        self._usb_stop = threading.Event()
        self._gadget: GadgetOffload | None = None

    def run(self) -> None:
        cfg = self._cfg
        recordings_root(cfg).mkdir(parents=True, exist_ok=True)

        self._hal = create_hal(cfg)
        hal = self._hal

        hal.led.set_colour_and_pattern(255, 255, 255, LedPattern.SLOW_PULSE)
        hal.display.update("BOOTING", {})

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

        # FR-12: Pi Zero 2W USB gadget mode — only on whisplay (Zero 2W) hardware.
        gadget = None
        if cfg.hardware.hat == "whisplay":
            gadget = GadgetOffload(recordings_root(cfg))
            gadget.start()
        self._gadget = gadget

        try:
            self._main_loop()
        finally:
            self._usb_stop.set()
            usb_thread.join(timeout=5.0)
            if gadget is not None:
                gadget.stop()
            hal.close()

    def _disk_blocked(self) -> bool:
        return is_over_disk_threshold(
            recordings_root(self._cfg),
            self._cfg.storage.disk_threshold_percent,
        )

    def _disk_pct_int(self) -> int:
        return round(disk_usage_percent(recordings_root(self._cfg)))

    def _sessions_count(self) -> int:
        root = recordings_root(self._cfg)
        if not root.exists():
            return 0
        return sum(1 for d in root.iterdir() if d.is_dir())

    def _set_idle_led(self, disk_blocked: bool) -> None:
        hal = self._hal
        assert hal is not None
        if disk_blocked:
            hal.led.set_colour_and_pattern(255, 128, 0, LedPattern.SLOW_PULSE)
        else:
            hal.led.set_colour_and_pattern(0, 255, 0, LedPattern.SOLID)
        now = datetime.now()
        hal.display.update(
            "IDLE",
            {
                "disk_pct": self._disk_pct_int(),
                "sessions_count": self._sessions_count(),
                "time": now.strftime("%a %b %-d %-I:%M%p").replace("AM","am").replace("PM","pm"),
            },
        )

    def _main_loop(self) -> None:
        hal = self._hal
        assert hal is not None
        while True:
            while self._disk_blocked():
                disk_pct = self._disk_pct_int()
                hal.led.set_colour_and_pattern(255, 128, 0, LedPattern.SLOW_PULSE)
                hal.display.update("DISK_FULL", {"disk_pct": disk_pct})
                time.sleep(0.5)

            # USB stick inserted while idle → offload immediately.
            if self._usb_stick_pending.is_set() and not self._usb_error.is_set():
                self._usb_offload()
                continue

            # USB gadget: cable detected → load g_mass_storage, wait for host.
            if self._gadget is not None and self._gadget.pending.is_set() and not self._gadget.is_active:
                if self._gadget.activate():
                    # g_mass_storage is loaded; wait for the host to enumerate.
                    # Show IDLE while waiting, TRANSFER once the host connects.
                    while self._gadget.is_active and not self._usb_stop.is_set():
                        if not self._gadget.pending.is_set():
                            break  # host disconnected → monitor deactivated
                        if hal.button.pressed():
                            # Button press exits transfer mode — user has finished.
                            _log.info("Button pressed during USB transfer — returning to idle")
                            self._gadget.deactivate()
                            self._gadget.pending.clear()
                            break
                        if self._gadget.host_connected.is_set():
                            hal.led.set_colour_and_pattern(0, 0, 255, LedPattern.SLOW_PULSE)
                            hal.display.update(
                                "USB_TRANSFER",
                                {"sessions_label": f"{self._sessions_count()} sessions"},
                            )
                        else:
                            self._set_idle_led(False)  # loaded but no host yet
                        time.sleep(0.5)
                self._set_idle_led(self._disk_blocked())
                continue

            self._set_idle_led(False)
            _log.info("Ready: green = idle, orange = disk full, press button to record.")

            transcribe_after = (
                time.monotonic() + 180.0
                if self._cfg.transcription.enabled
                else None
            )
            action = self._wait_idle_button(transcribe_after=transcribe_after)
            if action == "shutdown":
                self._shutdown_sequence()
                return
            if action == "transcribe":
                transcription_result = self._transcribing_session()
                if transcription_result == "button":
                    # Button pressed during transcription — start recording immediately.
                    if not self._disk_blocked():
                        if self._gadget is not None and self._gadget.is_active:
                            self._gadget.deactivate()
                        self._recording_session()
                # USB stick insertion or end of queue handled on next loop iteration.
                continue
            if action != "click":
                continue

            if self._disk_blocked():
                continue

            # If USB gadget is active (cable connected), deactivate before recording.
            if self._gadget is not None and self._gadget.is_active:
                self._gadget.deactivate()

            self._recording_session()

            # USB stick was inserted during recording → offload now that session is done.
            if self._usb_stick_pending.is_set() and not self._usb_error.is_set():
                self._usb_offload()
            # USB gadget was pending during recording → activate now.
            elif self._gadget is not None and self._gadget.pending.is_set() and not self._gadget.is_active:
                hal = self._hal
                assert hal is not None
                if self._gadget.activate():
                    while self._gadget.is_active and not self._usb_stop.is_set():
                        if not self._gadget.pending.is_set():
                            break
                        if hal.button.pressed():
                            _log.info("Button pressed during USB transfer — returning to idle")
                            self._gadget.deactivate()
                            self._gadget.pending.clear()
                            break
                        if self._gadget.host_connected.is_set():
                            hal.led.set_colour_and_pattern(0, 0, 255, LedPattern.SLOW_PULSE)
                            hal.display.update(
                                "USB_TRANSFER",
                                {"sessions_label": f"{self._sessions_count()} sessions"},
                            )
                        else:
                            self._set_idle_led(False)
                        time.sleep(0.5)
                self._set_idle_led(self._disk_blocked())

    def _wait_idle_button(self, transcribe_after: float | None = None) -> str:
        """Wait for a debounced short click (record), long hold (shutdown), or transcribe timeout."""
        hal = self._hal
        assert hal is not None
        hold = self._cfg.recording.shutdown_hold_seconds
        min_click_s = 0.03
        poll_s = 0.02
        heartbeat_deadline = time.monotonic() + 45.0

        def _usb_wants_offload() -> bool:
            return self._usb_stick_pending.is_set() and not self._usb_error.is_set()

        def _gadget_wants_activate() -> bool:
            return (
                self._gadget is not None
                and self._gadget.pending.is_set()
                and not self._gadget.is_active
            )

        while True:
            if _usb_wants_offload():
                return "usb"
            if _gadget_wants_activate():
                return "gadget"

            # Wait for a stable released state.
            while True:
                if _usb_wants_offload():
                    return "usb"
                if _gadget_wants_activate():
                    return "gadget"
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
                if _usb_wants_offload():
                    return "usb"
                if _gadget_wants_activate():
                    return "gadget"
                if transcribe_after is not None and time.monotonic() >= transcribe_after:
                    if pending_sessions(recordings_root(self._cfg)):
                        return "transcribe"
                    transcribe_after = time.monotonic() + 180.0  # re-arm for next check
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

            # Skip recovery if session.opus already exists (properly encoded session).
            if (session_dir / "session.opus").exists():
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

                # Keep WAV files for crash recovery and future analysis.
                # Do not delete wav_path.

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
        time.  WAV chunks (``recording-001.wav``, etc.) are kept during recording.
        When the button is pressed, all WAV chunks are concatenated into
        ``session.wav``, then transcribed. After transcription, the session.wav
        is encoded to opus for offload. The LED stays red throughout recording.
        """
        hal = self._hal
        assert hal is not None
        cfg = self._cfg
        self._snap_recording_led(hal)

        session_stamp = new_recording_stamp()
        session_dir = recording_directory(cfg, session_stamp)
        session_dir.mkdir(parents=True, exist_ok=True)
        session_start = time.monotonic()

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

            session_too_short = False
            chunk_num = 0
            # Mutable cell so the timer thread always sees the current chunk.
            _cur_chunk = [1]
            _stop_timer = threading.Event()

            def _display_timer() -> None:
                while not _stop_timer.wait(1.0):
                    elapsed = int(time.monotonic() - session_start)
                    timer_str = (
                        f"{elapsed // 3600:02d}:"
                        f"{(elapsed % 3600) // 60:02d}:"
                        f"{elapsed % 60:02d}"
                    )
                    try:
                        hal.display.update(
                            "RECORDING",
                            {
                                "chunk_num": _cur_chunk[0],
                                "session_timer": timer_str,
                                "disk_pct": self._disk_pct_int(),
                            },
                        )
                    except Exception:
                        pass

            timer_thread = threading.Thread(
                target=_display_timer,
                name="earshot-rec-timer",
                daemon=True,
            )
            timer_thread.start()

            try:
                while True:
                    chunk_num += 1
                    _cur_chunk[0] = chunk_num
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
                        if reason == "button":
                            session_too_short = True
                        if reason == "button":
                            break
                        continue

                    # WAV chunk is kept for later concatenation and transcription.
                    _log.info("Recorded chunk %d: %.0fs", chunk_num, duration_s)

                    if reason == "button":
                        break
                    _log.info("Rolling over to chunk %d after %.0fs", chunk_num + 1, duration_s)

            finally:
                _stop_timer.set()
                timer_thread.join(timeout=2.0)
                try:
                    audio.stop()
                except Exception:
                    pass
                audio.close()

            if session_too_short:
                shutil.rmtree(session_dir, ignore_errors=True)
                flash_double_green(hal)
                self._set_idle_led(self._disk_blocked())
                return

            # Show amber LED while encoding (post-recording processing).
            hal.led.set_colour_and_pattern(255, 180, 0, LedPattern.SLOW_PULSE)

            # Recording complete. Concatenate all WAV chunks into a single session.wav for transcription.
            session_wav = session_dir / "session.wav"
            try:
                concat_wav_files(session_dir, session_wav)
            except Exception as exc:
                _log.error("Failed to concatenate WAV files for %s: %s", session_dir.name, exc)
                # Leave the individual WAV files if concatenation fails
                pass

            # Encode session.wav to opus stereo for offload.
            session_opus = session_dir / "session.opus"
            if session_wav.exists():
                try:
                    wav_to_opus_stereo(
                        session_wav,
                        session_opus,
                        sample_rate=cfg.audio.sample_rate,
                        bitrate_kbps=cfg.audio.opus_bitrate,
                    )
                    # Delete session.wav immediately after successful encoding (transcription uses opus).
                    session_wav.unlink(missing_ok=True)
                except Exception as exc:
                    _log.error("Failed to encode opus for %s: %s", session_dir.name, exc)
                    # Continue without opus; transcription can still happen

            # Save status for earshot-tui.
            # Extract duration from session.opus if it exists.
            duration_s = 0.0
            session_opus = session_dir / "session.opus"
            if session_opus.exists():
                try:
                    result = subprocess.run(
                        [
                            "ffprobe",
                            "-v", "error",
                            "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1:csv=p=0",
                            str(session_opus),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        duration_s = float(result.stdout.strip())
                except Exception as exc:
                    _log.warning("Failed to extract duration from %s: %s", session_opus.name, exc)

            status = Status(
                status="recorded",
                device="earshot",
                recorded_at=datetime.now(),
                duration=duration_s,
            )
            save_status(session_dir, status)

            # Remove session dir if encoding left nothing behind.
            try:
                session_dir.rmdir()
            except OSError:
                pass

            # Return to idle (green).
            self._set_idle_led(self._disk_blocked())

        except Exception:
            _log.exception("unexpected error in recording session")
            self._set_idle_led(self._disk_blocked())


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

    # ── Transcription (FR-14–FR-17) ──────────────────────────────────────────

    def _transcribing_session(self) -> str:
        """Process the transcription queue.

        Iterates the pending queue FIFO, transcribing each session.  Returns:
        - ``"button"`` if the user presses the button to start recording
        - ``"usb"`` if a USB stick is inserted
        - ``"done"`` when the queue empties or a failure stops processing
        """
        hal = self._hal
        assert hal is not None
        cfg = self._cfg

        models_dir = Path.home() / ".local/share/earshot/models"
        try:
            model = WhisperModel(
                cfg.transcription.model,
                device="cpu",
                download_root=str(models_dir),
                cpu_threads=cfg.transcription.threads,
            )
        except Exception as exc:
            _log.error("Failed to load WhisperModel: %s", exc)
            return "done"

        queue = pending_sessions(recordings_root(cfg))
        total = len(queue)
        transcribed = 0

        while queue:
            session_dir = queue[0]
            pos = transcribed + 1

            hal.led.set_colour_and_pattern(255, 179, 0, LedPattern.VERY_SLOW_PULSE)
            hal.display.update(
                "TRANSCRIBING",
                {
                    "queue_pos": pos,
                    "queue_total": total,
                    "session": session_dir.name,
                },
            )

            cancel = threading.Event()
            result_holder: list[list[dict] | None] = [None]

            def _run(sd=session_dir, rh=result_holder, c=cancel, m=model) -> None:
                rh[0] = transcribe_session(sd, m, c)

            t = threading.Thread(
                target=_run,
                name=f"earshot-transcribe-{session_dir.name}",
                daemon=True,
            )
            t.start()

            button_pressed = False
            usb_pending = False
            while t.is_alive():
                if hal.button.pressed():
                    cancel.set()
                    t.join(timeout=10.0)
                    button_pressed = True
                    break
                if self._usb_stick_pending.is_set():
                    cancel.set()
                    t.join(timeout=10.0)
                    usb_pending = True
                    break
                time.sleep(0.1)

            if not button_pressed and not usb_pending:
                t.join()

            if button_pressed:
                return "button"

            if usb_pending:
                return "usb"

            result = result_holder[0]
            if result is None:
                _log.error(
                    "Transcription failed for %s — will retry on next idle window",
                    session_dir.name,
                )
                return "done"

            write_transcript(session_dir, result)

            # Update status to transcribed for earshot-tui.
            status = load_status(session_dir)
            if status is not None:
                status.status = "transcribed"
                status.transcribed_at = datetime.now()
                save_status(session_dir, status)

            transcribed += 1
            queue.pop(0)

            # Re-scan in case new sessions arrived while we were transcribing.
            queue = pending_sessions(recordings_root(cfg))
            total = transcribed + len(queue)

        return "done"

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

        sessions_label = f"{self._sessions_count()} sessions"
        hal.led.set_colour_and_pattern(0, 0, 255, LedPattern.SLOW_PULSE)
        hal.display.update(
            "USB_TRANSFER",
            {"sessions_label": sessions_label, "disk_pct": self._disk_pct_int()},
        )

        # Wait up to 10 s for the systemd mount service to finish.
        info = None
        mount = None
        for _ in range(20):
            info = find_usb_device()
            if info and info[1]:
                mount = Path(info[1])
                break
            time.sleep(0.5)

        if mount is None:
            _log.warning("USB stick not mounted after waiting — skipping offload")
            self._usb_stick_pending.clear()
            self._set_idle_led(self._disk_blocked())
            return

        device = info[0]  # type: ignore[index]
        try:
            move_recordings_to_stick(recordings_root(self._cfg), mount)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                _log.error("USB stick full — some recordings remain on device")
                error_reason = "Stick full"
            else:
                _log.error("USB offload error: %s", exc)
                error_reason = str(exc)
            self._usb_error.set()
            hal.led.set_colour_and_pattern(255, 128, 0, LedPattern.SLOW_PULSE)
            hal.display.update("USB_TRANSFER_ERROR", {"error_reason": error_reason})
            return

        eject_usb_device(device)
        _log.info("USB offload complete")
        hal.display.update("USB_TRANSFER_COMPLETE", {})
        flash_single_blue(hal)
        self._usb_stick_pending.clear()
        self._set_idle_led(self._disk_blocked())

    # ── Shutdown ─────────────────────────────────────────────────────────────

    def _shutdown_sequence(self) -> None:
        hal = self._hal
        assert hal is not None
        hal.led.set_colour_and_pattern(255, 255, 255, LedPattern.SLOW_PULSE)
        hal.display.update("SHUTDOWN", {})
        time.sleep(1.0)
        if hal.animator is not None:
            hal.animator.run_fade_off(2.0)
        _log.info("requesting system poweroff")
        try:
            import ctypes
            # CAP_SYS_BOOT allows calling reboot(2) directly.
            # LINUX_REBOOT_CMD_POWER_OFF = 0x4321fedc
            ctypes.CDLL("libc.so.6").reboot(0x4321fedc)
        except Exception as exc:
            _log.warning("poweroff via libc failed (%s); falling back to systemctl", exc)
            subprocess.run(["systemctl", "poweroff", "--no-wall"], check=False)
