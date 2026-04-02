"""Runtime hardware bundle (LED handle, button, audio factory, cleanup)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from earshot.hal.protocols import AudioCapture, ButtonDriver, DisplayDriver, LEDDriver

if TYPE_CHECKING:
    from earshot.hal.animator import LedAnimator
    from earshot.hal.pi import PiLED


@dataclass
class Hal:
    led: LEDDriver
    button: ButtonDriver
    display: DisplayDriver
    pi_led: PiLED | None
    animator: LedAnimator | None
    _audio_factory: Callable[[], AudioCapture]
    _on_close: Callable[[], None]

    def new_audio_capture(self) -> AudioCapture:
        return self._audio_factory()

    def close(self) -> None:
        self._on_close()
