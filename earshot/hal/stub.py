"""Stub hardware for development off the Pi (ADR-0003)."""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Any

from earshot.hal.protocols import AudioCapture, ButtonDriver, DisplayDriver, LEDDriver, LedPattern

_log = logging.getLogger(__name__)


class StubLED(LEDDriver):
    def set_colour_and_pattern(
        self,
        red: int,
        green: int,
        blue: int,
        pattern: LedPattern,
    ) -> None:
        _log.info("stub LED: rgb=(%s,%s,%s) pattern=%s", red, green, blue, pattern.name)

    def close(self) -> None:
        pass


class StubButton(ButtonDriver):
    """Treat the button as released unless `inject_press()` is called (tests)."""

    def __init__(self) -> None:
        self._held = False
        self._lock = threading.Lock()

    def inject_press(self, held: bool) -> None:
        with self._lock:
            self._held = held

    def pressed(self) -> bool:
        with self._lock:
            return self._held

    def close(self) -> None:
        pass


class StdinPulseButton(ButtonDriver):
    """While stdin is a TTY, each Enter emulates a short click (press then release)."""

    def __init__(self) -> None:
        self._pressed_until: float = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()

        if sys.stdin.isatty():
            self._thread = threading.Thread(target=self._run, name="earshot-stub-button", daemon=True)
            self._thread.start()
        else:
            self._thread = None
            _log.warning(
                "stub button: stdin is not a TTY — button inactive. "
                "Use EARSHOT_HAL=stub with a TTY, or run on a Pi."
            )

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                line = sys.stdin.readline()
            except OSError:
                break
            if not line:
                break
            with self._lock:
                self._pressed_until = time.monotonic() + 0.15

    def pressed(self) -> bool:
        with self._lock:
            return time.monotonic() < self._pressed_until

    def close(self) -> None:
        self._stop.set()


class StubDisplay(DisplayDriver):
    """Prints display state to stdout — fully observable without a Pi."""

    def update(self, state: str, data: dict[str, Any]) -> None:
        parts = [f"[DISPLAY] state={state}"]
        for key, val in sorted(data.items()):
            parts.append(f"{key}={val}")
        _log.info(" ".join(parts))

    def close(self) -> None:
        pass


class StubAudioCapture(AudioCapture):
    """Emits silence (zeros) for timing tests."""

    def __init__(self, channels: int, sample_rate: int) -> None:
        self._channels = channels
        self._sample_rate = sample_rate
        self._active = False

    def start(self) -> None:
        self._active = True

    def read_frames(self, num_frames: int) -> bytes:
        if not self._active:
            return b"\x00" * (num_frames * self._channels * 2)
        return b"\x00" * (num_frames * self._channels * 2)

    def stop(self) -> None:
        self._active = False

    def close(self) -> None:
        self._active = False
