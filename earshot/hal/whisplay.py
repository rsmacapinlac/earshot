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
# The LED is common-anode (active-low): set active_high=False in gpiozero.
_GPIO_RED = 25
_GPIO_GREEN = 24
_GPIO_BLUE = 23

# GPIO BCM pin numbers for the ST7789P3 SPI display.
_GPIO_DC = 27     # Data/Command select
_GPIO_RST = 4     # Reset
_GPIO_BL = 22     # Backlight enable (active-low)

# LED animation timing (mirrors LedAnimator in animator.py)
_SLOW_PERIOD_S = 1.0
_FAST_BLINK_PERIOD_S = 0.2

# LCD geometry (240×280 px, ST7789P3)
_LCD_WIDTH = 240
_LCD_HEIGHT = 280
_LCD_Y_OFFSET = 20  # panel has 20 invisible rows at top (rounded corners)

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

# ASCII logo animation frames (ADR-0014).
# Full mark is 7 lines — dot, 3 arc pairs, dot — symmetric, expands outward.
LOGO_FRAMES = [
    "·",                               # 1 line  — dot only
    "·\n )\n·",                        # 3 lines — 1 arc pair
    "·\n )\n ))\n ))\n )\n·",         # 6 lines — 2 arc pairs
    "·\n )\n ))\n )))\n ))\n )\n·",   # 7 lines — full mark (maximum)
    "·\n )\n ))\n ))\n )\n·",         # 6 lines — collapsing
    "·\n )\n·",                        # 3 lines — collapsing
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


# ── ST7789 raw SPI driver ─────────────────────────────────────────────────────

class _ST7789:
    """Minimal ST7789P3 driver using spidev + RPi.GPIO.

    Uses the exact init sequence from the PiSugar whisplay-ai-chatbot reference
    implementation (USE_HORIZONTAL=1, MADCTL=0xC0, RGB565, 20-row Y offset).
    """

    def __init__(self, dc: int, rst: int) -> None:
        import spidev
        import RPi.GPIO as GPIO  # type: ignore[import-untyped]

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(dc, GPIO.OUT)
        GPIO.setup(rst, GPIO.OUT)
        self._dc = dc
        self._rst = rst
        self._GPIO = GPIO

        self._spi = spidev.SpiDev()
        self._spi.open(0, 0)
        self._spi.max_speed_hz = 40_000_000
        self._spi.mode = 0b00

        self._reset()
        self._init()

    # ── low-level helpers ─────────────────────────────────────────────────────

    def _out(self, pin: int, val: int) -> None:
        self._GPIO.output(pin, val)

    def _cmd(self, cmd: int, *data: int) -> None:
        self._out(self._dc, 0)
        self._spi.xfer2([cmd])
        if data:
            self._out(self._dc, 1)
            self._spi.writebytes2(list(data))

    def _data(self, buf: bytes | bytearray) -> None:
        self._out(self._dc, 1)
        chunk = 4096
        mv = memoryview(buf)
        for i in range(0, len(mv), chunk):
            self._spi.writebytes2(mv[i : i + chunk])

    # ── init ─────────────────────────────────────────────────────────────────

    def _reset(self) -> None:
        self._out(self._rst, 1); time.sleep(0.1)
        self._out(self._rst, 0); time.sleep(0.1)
        self._out(self._rst, 1); time.sleep(0.12)

    def _init(self) -> None:
        self._cmd(0x11)           # Sleep Out
        time.sleep(0.12)
        self._cmd(0x36, 0xC0)    # MADCTL — MY=1, MX=1 (USE_HORIZONTAL=1)
        self._cmd(0x3A, 0x05)    # COLMOD — RGB565
        self._cmd(0xB2, 0x0C, 0x0C, 0x00, 0x33, 0x33)  # PORCTR
        self._cmd(0xB7, 0x35)    # GCTRL
        self._cmd(0xBB, 0x32)    # VCOMS
        self._cmd(0xC2, 0x01)    # VDVS
        self._cmd(0xC3, 0x15)    # VRHS
        self._cmd(0xC4, 0x20)    # VDVSET
        self._cmd(0xC6, 0x0F)    # FRCTRL2
        self._cmd(0xD0, 0xA4, 0xA1)  # PWCTRL1
        self._cmd(0xE0, 0xD0, 0x08, 0x0E, 0x09, 0x09, 0x05,
                  0x31, 0x33, 0x48, 0x17, 0x14, 0x15, 0x31, 0x34)
        self._cmd(0xE1, 0xD0, 0x08, 0x0E, 0x09, 0x09, 0x15,
                  0x31, 0x33, 0x48, 0x17, 0x14, 0x15, 0x31, 0x34)
        self._cmd(0x21)           # INVON — display inversion on
        self._cmd(0x29)           # DISPON

    # ── public API ────────────────────────────────────────────────────────────

    def display(self, image: Any) -> None:
        """Send a PIL Image (RGB mode) to the display."""
        img = image.convert("RGB").resize((_LCD_WIDTH, _LCD_HEIGHT))
        # Set column address 0–239, row address 20–299 (20-row offset)
        y0 = _LCD_Y_OFFSET
        y1 = _LCD_Y_OFFSET + _LCD_HEIGHT - 1
        self._cmd(0x2A, 0, 0, 0, _LCD_WIDTH - 1)
        self._cmd(0x2B, y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)
        self._cmd(0x2C)
        # Convert RGB888 → RGB565 big-endian
        pixels = img.tobytes()
        buf = bytearray(_LCD_WIDTH * _LCD_HEIGHT * 2)
        j = 0
        for i in range(0, len(pixels), 3):
            r = pixels[i] >> 3
            g = pixels[i + 1] >> 2
            b = pixels[i + 2] >> 3
            rgb565 = (r << 11) | (g << 5) | b
            buf[j] = (rgb565 >> 8) & 0xFF
            buf[j + 1] = rgb565 & 0xFF
            j += 2
        self._data(buf)

    def cleanup(self) -> None:
        try:
            self._spi.close()
        except Exception:
            pass
        try:
            self._GPIO.cleanup([self._dc, self._rst])
        except Exception:
            pass


# ── WhisplayLED ───────────────────────────────────────────────────────────────

class WhisplayLED(LEDDriver):
    """Drives the Whisplay HAT's three discrete GPIO RGB LEDs.

    Uses a background thread for animated patterns (SLOW_PULSE, FAST_BLINK)
    with a sine-wave brightness curve, mirroring the APA102 LedAnimator
    approach used for the ReSpeaker HAT.
    """

    def __init__(self) -> None:
        from gpiozero import RGBLED  # type: ignore[import-untyped]

        self._rgb = RGBLED(red=_GPIO_RED, green=_GPIO_GREEN, blue=_GPIO_BLUE, active_high=False)
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
    """Renders state to the Whisplay HAT's 240×280 ST7789P3 LCD.

    Uses a direct spidev driver with the exact init sequence from the PiSugar
    whisplay-ai-chatbot reference implementation.

    Layout (ADR-0014, display.md):
        Zone A (~60px)  — state label, accent colour, bold
        Zone B (~120px) — ASCII arc logo, centred, accent colour
        Zone C (~60px)  — primary data (large, white or accent)
        Zone D (~40px)  — secondary data (small, muted #888888)
    """

    def __init__(self, brightness: int = 80) -> None:
        self._brightness = max(0, min(100, brightness))
        self._bl_pin = None
        self._device: _ST7789 | None = None
        self._frame_idx = 0
        self._lock = threading.Lock()
        self._font_large = None
        self._font_medium = None
        self._font_small = None
        self._init()

    def _init(self) -> None:
        try:
            self._device = _ST7789(_GPIO_DC, _GPIO_RST)
            self._bl_pin = self._init_backlight()
            self._load_fonts()
            _log.info("WhisplayDisplay ready (%dx%d)", _LCD_WIDTH, _LCD_HEIGHT)
        except Exception as exc:
            _log.error("WhisplayDisplay init failed: %s — display disabled", exc)
            self._device = None

    def _init_backlight(self):
        try:
            from gpiozero import LED as GpioLED  # type: ignore[import-untyped]
            bl = GpioLED(_GPIO_BL, active_high=False)
            bl.on()
            return bl
        except Exception as exc:
            _log.warning("Backlight GPIO init failed: %s", exc)
            return None

    def _load_fonts(self) -> None:
        from PIL import ImageFont
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
        ]
        for path in candidates:
            try:
                self._font_large = ImageFont.truetype(path, 28)
                self._font_medium = ImageFont.truetype(path, 20)
                self._font_small = ImageFont.truetype(path, 14)
                _log.debug("Loaded font: %s", path)
                return
            except (OSError, IOError):
                continue
        # PIL built-in bitmap font — tiny but always available
        default = ImageFont.load_default()
        self._font_large = default
        self._font_medium = default
        self._font_small = default
        _log.debug("Using PIL default font")

    def update(self, state: str, data: dict[str, Any]) -> None:
        if self._device is None:
            return
        try:
            from PIL import Image, ImageDraw

            colour = _PALETTE.get(state, _DEFAULT_COLOUR)
            accent = "#{:02X}{:02X}{:02X}".format(*colour)
            bg = "#0D0D0D"
            white = "#FFFFFF"
            muted = "#888888"

            zone_a_label = _ZONE_A_LABELS.get(state, state)

            with self._lock:
                if state == "IDLE":
                    self._frame_idx = 3
                else:
                    self._frame_idx = (self._frame_idx + 1) % len(LOGO_FRAMES)
                logo_text = LOGO_FRAMES[self._frame_idx]

            zone_c = _zone_c(state, data)
            zone_d = _zone_d(state, data)

            img = Image.new("RGB", (_LCD_WIDTH, _LCD_HEIGHT), bg)
            draw = ImageDraw.Draw(img)

            # Zone A (~60px)  — state label
            draw.text((12, 8), zone_a_label, fill=accent, font=self._font_large)
            # Zone B (~120px) — logo, small font so 7 lines fit
            draw.text((20, 65), logo_text, fill=accent, font=self._font_small)
            # Zone C (~60px)  — primary data (font_small leaves room for two lines)
            draw.text((12, 195), zone_c, fill=white, font=self._font_small)
            # Zone D (~40px)  — secondary data
            draw.text((12, 248), zone_d, fill=muted, font=self._font_small)

            self._device.display(img)
        except Exception as exc:
            _log.debug("WhisplayDisplay.update error: %s", exc)

    def close(self) -> None:
        if self._bl_pin is not None:
            try:
                self._bl_pin.off()
                self._bl_pin.close()
            except Exception as exc:
                _log.debug("WhisplayDisplay backlight close: %s", exc)
        if self._device is not None:
            try:
                self._device.cleanup()
            except Exception as exc:
                _log.debug("WhisplayDisplay close: %s", exc)


def _zone_c(state: str, data: dict[str, Any]) -> str:
    """Primary data line for each state."""
    if state == "BOOTING":
        return "Starting..."
    if state == "IDLE":
        time_str = data.get("time", "--:--")
        date_str = data.get("date", "")
        return f"{time_str}\n{date_str}" if date_str else time_str
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
