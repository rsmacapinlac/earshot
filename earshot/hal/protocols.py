"""Hardware abstraction (ADR-0003)."""

from __future__ import annotations

from enum import Enum, auto
from typing import Any, Protocol, runtime_checkable


class LedPattern(Enum):
    OFF = auto()
    SOLID = auto()
    SLOW_PULSE = auto()
    FAST_BLINK = auto()
    FADE_OFF = auto()
    DOUBLE_FLASH_GREEN = auto()


@runtime_checkable
class LEDDriver(Protocol):
    """Drives the single indicator LED (first APA102 on the ReSpeaker HAT, v1)."""

    def set_colour_and_pattern(
        self,
        red: int,
        green: int,
        blue: int,
        pattern: LedPattern,
    ) -> None:
        """Update target colour (0–255) and animation pattern."""

    def close(self) -> None:
        """Release hardware (SPI, etc.)."""


@runtime_checkable
class ButtonDriver(Protocol):
    """User button on GPIO17 (active low)."""

    def pressed(self) -> bool:
        """True while the button is held down."""

    def close(self) -> None:
        """Release GPIO resources."""


@runtime_checkable
class AudioCapture(Protocol):
    """Stereo PCM capture at the configured sample rate."""

    def start(self) -> None: ...

    def read_frames(self, num_frames: int) -> bytes:
        """Return interleaved int16 little-endian PCM (stereo)."""

    def stop(self) -> None: ...

    def close(self) -> None: ...


@runtime_checkable
class DisplayDriver(Protocol):
    """LCD display on Whisplay HAT; no-op on ReSpeaker (ADR-0009)."""

    def update(self, state: str, data: dict[str, Any]) -> None:
        """Render the given device state and supplementary data to the display.

        ``state`` is the string name of the current ``DeviceState`` (e.g.
        ``"IDLE"``, ``"RECORDING"``).  ``data`` carries optional context keys
        such as ``session_timer``, ``chunk_num``, ``disk_pct``.
        """

    def close(self) -> None:
        """Release display resources (backlight off, SPI closed)."""
