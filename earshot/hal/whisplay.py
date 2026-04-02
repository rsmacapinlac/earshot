"""Whisplay HAT hardware: GPIO RGB LED and ST7789P3 LCD display (ADR-0013, ADR-0014)."""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any

from earshot.hal.protocols import DisplayDriver, LEDDriver, LedPattern

_log = logging.getLogger(__name__)

# GPIO BCM pin numbers for the Whisplay HAT's discrete RGB LED.
_GPIO_RED = 25
_GPIO_GREEN = 24
_GPIO_BLUE = 23

# LED animation timing (mirrors LedAnimator in animator.py)
_SLOW_PERIOD_S = 1.0
_FAST_BLINK_PERIOD_S = 0.2

# LCD geometry (240×280 px, ST7789P3)
_LCD_WIDTH = 240
_LCD_HEIGHT = 280

# Display state colour palette (hex → RGB) — from display.md
_PALETTE: dict[str, tuple[int, int, int]] = {
    "BOOTING": (255, 255, 255),
    "IDLE": (0, 204, 68),
    "RECORDING": (255, 48, 48),
    "ENCODING": (32, 128, 255),
    "ENCODE_FAILED": (255, 48, 48),
    "USB_TRANSFER": (32, 128, 255),
    "USB_TRANSFER_COMPLETE": (32, 128, 255),
    "USB_TRANSFER_ERROR": (255, 128, 0),
    "DISK_FULL": (255, 128, 0),
    "SHUTDOWN": (255, 255, 255),
}
_DEFAULT_COLOUR = (255, 255, 255)

# ASCII logo animation frames (ADR-0014)
LOGO_FRAMES = [
    "·",
    "·\n )",
    "·\n )\n ))",
    "·\n )\n ))\n )))",
    "·\n )\n ))",
    "·\n )",
]

# Zone A labels per state
_ZONE_A_LABELS: dict[str, str] = {
    "BOOTING": "EARSHOT",
    "IDLE": "READY",
    "RECORDING": "● REC",
    "ENCODING": "ENCODING",
    "ENCODE_FAILED": "ENCODE FAILED",
    "USB_TRANSFER": "TRANSFER",
    "USB_TRANSFER_COMPLETE": "DONE",
    "USB_TRANSFER_ERROR": "TRANSFER ERROR",
    "DISK_FULL": "STORAGE FULL",
    "SHUTDOWN": "GOODBYE",
}


# ── WhisplayLED ───────────────────────────────────────────────────────────────

class WhisplayLED(LEDDriver):
    """Drives the Whisplay HAT's three discrete GPIO RGB LEDs.

    Uses a background thread for animated patterns (SLOW_PULSE, FAST_BLINK)
    with a sine-wave brightness curve, mirroring the APA102 LedAnimator
    approach used for the ReSpeaker HAT.
    """

    def __init__(self) -> None:
        from gpiozero import RGBLED  # type: ignore[import-untyped]

        self._rgb = RGBLED(red=_GPIO_RED, green=_GPIO_GREEN, blue=_GPIO_BLUE)
        self._lock = threading.Lock()
        self._red = 255
        self._green = 255
        self._blue = 255
        self._pattern = LedPattern.SLOW_PULSE
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="earshot-whisplay-led",
            daemon=True,
        )
        self._thread.start()

    def set_colour_and_pattern(
        self,
        red: int,
        green: int,
        blue: int,
        pattern: LedPattern,
    ) -> None:
        with self._lock:
            self._red = max(0, min(255, red))
            self._green = max(0, min(255, green))
            self._blue = max(0, min(255, blue))
            self._pattern = pattern

        if pattern == LedPattern.SOLID:
            self._apply(red, green, blue, 1.0)
        elif pattern in (LedPattern.OFF, LedPattern.FADE_OFF):
            self._apply(red, green, blue, 0.0)

    def _apply(self, r: int, g: int, b: int, brightness: float) -> None:
        self._rgb.color = (
            r / 255.0 * brightness,
            g / 255.0 * brightness,
            b / 255.0 * brightness,
        )

    def _run(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            with self._lock:
                pattern = self._pattern
                r, g, b = self._red, self._green, self._blue

            if pattern in (LedPattern.SOLID, LedPattern.OFF, LedPattern.FADE_OFF,
                           LedPattern.DOUBLE_FLASH_GREEN):
                time.sleep(0.05)
                continue

            if pattern == LedPattern.SLOW_PULSE:
                phase = (now % _SLOW_PERIOD_S) / _SLOW_PERIOD_S
                brightness = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(phase * 2 * math.pi))
                self._apply(r, g, b, brightness)
            elif pattern == LedPattern.FAST_BLINK:
                on = int(now / _FAST_BLINK_PERIOD_S) % 2 == 0
                self._apply(r, g, b, 1.0 if on else 0.0)

            time.sleep(0.02)

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        try:
            self._rgb.off()
            self._rgb.close()
        except Exception as exc:
            _log.debug("WhisplayLED close: %s", exc)


# ── WhisplayDisplay ───────────────────────────────────────────────────────────

class WhisplayDisplay(DisplayDriver):
    """Renders state to the Whisplay HAT's 240×280 ST7789P3 LCD via luma.lcd.

    Layout (ADR-0014, display.md):
        Zone A (~60px)  — state label, accent colour, bold
        Zone B (~120px) — ASCII arc logo, centred, accent colour
        Zone C (~60px)  — primary data (large, white or accent)
        Zone D (~40px)  — secondary data (small, muted #888888)
    """

    def __init__(self, brightness: int = 80) -> None:
        self._brightness = max(0, min(100, brightness))
        self._device = self._init_device()
        self._frame_idx = 0
        self._lock = threading.Lock()

    def _init_device(self):
        try:
            from luma.core.interface.serial import spi
            from luma.lcd.device import st7789

            serial = spi(port=0, device=0, gpio_DC=25, gpio_RST=27)
            device = st7789(serial, width=_LCD_WIDTH, height=_LCD_HEIGHT, rotate=0)
            device.backlight(self._brightness > 0)
            return device
        except Exception as exc:
            _log.error("WhisplayDisplay init failed: %s — display disabled", exc)
            return None

    def update(self, state: str, data: dict[str, Any]) -> None:
        if self._device is None:
            return
        try:
            from luma.core.render import canvas
            from PIL import ImageFont

            colour = _PALETTE.get(state, _DEFAULT_COLOUR)
            hex_colour = "#{:02X}{:02X}{:02X}".format(*colour)
            bg = "#0D0D0D"
            muted = "#888888"

            zone_a_label = _ZONE_A_LABELS.get(state, state)

            # Advance logo frame index for animated states; hold at max for IDLE
            with self._lock:
                if state == "IDLE":
                    self._frame_idx = 3  # frame 4 (0-indexed 3) = maximum
                else:
                    self._frame_idx = (self._frame_idx + 1) % len(LOGO_FRAMES)
                logo_text = LOGO_FRAMES[self._frame_idx]

            zone_c = _zone_c(state, data)
            zone_d = _zone_d(state, data)

            with canvas(self._device) as draw:
                draw.rectangle(
                    [(0, 0), (_LCD_WIDTH - 1, _LCD_HEIGHT - 1)],
                    fill=bg,
                )
                # Zone A — state label
                draw.text((10, 8), zone_a_label, fill=hex_colour)
                # Zone B — logo
                draw.text((10, 70), logo_text, fill=hex_colour)
                # Zone C — primary data
                draw.text((10, 200), zone_c, fill="#FFFFFF")
                # Zone D — secondary data
                draw.text((10, 250), zone_d, fill=muted)

        except Exception as exc:
            _log.debug("WhisplayDisplay.update error: %s", exc)

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.backlight(False)
                self._device.cleanup()
            except Exception as exc:
                _log.debug("WhisplayDisplay close: %s", exc)


def _zone_c(state: str, data: dict[str, Any]) -> str:
    """Primary data line for each state."""
    if state == "BOOTING":
        return "Starting..."
    if state == "IDLE":
        return data.get("time", "--:--")
    if state == "RECORDING":
        return data.get("session_timer", "00:00:00")
    if state in ("ENCODING", "ENCODE_FAILED"):
        chunk = data.get("chunk_num", "?")
        total = data.get("total_chunks", "?")
        return f"Chunk {chunk} of {total}"
    if state in ("USB_TRANSFER", "USB_TRANSFER_COMPLETE"):
        return data.get("sessions_label", "")
    if state == "USB_TRANSFER_ERROR":
        return data.get("error_reason", "Transfer error")
    if state == "DISK_FULL":
        pct = data.get("disk_pct", "?")
        return f"{pct}% used"
    if state == "SHUTDOWN":
        return "Safe to unplug soon"
    return ""


def _zone_d(state: str, data: dict[str, Any]) -> str:
    """Secondary data line for each state."""
    disk_pct = data.get("disk_pct")
    sessions = data.get("sessions_count")

    if state == "IDLE":
        parts = []
        if sessions is not None:
            parts.append(f"{sessions} sessions")
        if disk_pct is not None:
            parts.append(f"{disk_pct}% disk")
        return " · ".join(parts)
    if state == "RECORDING":
        chunk = data.get("chunk_num", "?")
        parts = [f"Chunk {chunk}"]
        if disk_pct is not None:
            parts.append(f"{disk_pct}% disk")
        return " · ".join(parts)
    if state == "ENCODING":
        return f"{disk_pct}% disk" if disk_pct is not None else ""
    if state == "ENCODE_FAILED":
        return "WAV file retained"
    if state == "USB_TRANSFER_COMPLETE":
        return "Safe to remove"
    if state == "USB_TRANSFER_ERROR":
        return "Remove stick to continue"
    if state == "DISK_FULL":
        return "Remove files to record"
    if state == "USB_TRANSFER":
        return f"{disk_pct}% disk" if disk_pct is not None else ""
    return ""
