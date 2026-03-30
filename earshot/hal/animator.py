"""Background LED animation for Pi hardware."""

from __future__ import annotations

import math
import threading
import time

from earshot.hal.protocols import LedPattern

_SLOW_PERIOD_S = 1.0
_FAST_BLINK_PERIOD_S = 0.2


class LedAnimator:
    """Updates a `PiLED` from a background thread while pattern is non-solid."""

    def __init__(self, led: PiLED) -> None:
        self._led = led
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._red = 255
        self._green = 255
        self._blue = 255
        self._pattern = LedPattern.SLOW_PULSE

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="earshot-led", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._stop.clear()

    def close(self) -> None:
        self.stop()
        self._led.close()

    def set_colour_and_pattern(
        self,
        red: int,
        green: int,
        blue: int,
        pattern: LedPattern,
    ) -> None:
        with self._lock:
            self._red = red
            self._green = green
            self._blue = blue
            self._pattern = pattern

        if pattern in (LedPattern.SOLID, LedPattern.OFF, LedPattern.FADE_OFF, LedPattern.DOUBLE_FLASH_GREEN):
            self._apply_immediate(red, green, blue, pattern)

    def _apply_immediate(
        self,
        red: int,
        green: int,
        blue: int,
        pattern: LedPattern,
    ) -> None:
        self._led.set_target_rgb(red, green, blue)
        if pattern == LedPattern.OFF:
            self._led.render_scaled(0.0)
        elif pattern == LedPattern.FADE_OFF:
            self._led.render_scaled(1.0)
        else:
            self._led.render_scaled(1.0)

    def run_fade_off(self, duration_s: float = 2.0) -> None:
        """Blocking fade to off (used during shutdown sequence)."""
        t0 = time.monotonic()
        self._led.set_target_rgb(255, 255, 255)
        while True:
            elapsed = time.monotonic() - t0
            if elapsed >= duration_s:
                self._led.render_scaled(0.0)
                return
            self._led.render_scaled(1.0 - elapsed / duration_s)
            time.sleep(0.04)

    def _run(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            with self._lock:
                pattern = self._pattern
                r, g, b = self._red, self._green, self._blue

            if pattern in (LedPattern.SOLID, LedPattern.OFF, LedPattern.FADE_OFF, LedPattern.DOUBLE_FLASH_GREEN):
                time.sleep(0.05)
                continue

            self._led.set_target_rgb(r, g, b)
            if pattern == LedPattern.SLOW_PULSE:
                phase = (now % _SLOW_PERIOD_S) / _SLOW_PERIOD_S
                factor = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(phase * 2 * math.pi))
                self._led.render_scaled(factor)
            elif pattern == LedPattern.FAST_BLINK:
                on = int(now / _FAST_BLINK_PERIOD_S) % 2 == 0
                self._led.render_scaled(1.0 if on else 0.0)

            time.sleep(0.02)
