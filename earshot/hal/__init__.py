"""Hardware abstraction layer factory."""

from __future__ import annotations

import logging
import os

from earshot.config import AppConfig
from earshot.hal.animator import LedAnimator
from earshot.hal.bundle import Hal
from earshot.hal.pi import PiAlsaCapture, PiAudioCapture, PiButton, PiLED
from earshot.hal.protocols import AudioCapture, ButtonDriver, LEDDriver, LedPattern
from earshot.hal.stub import StubAudioCapture, StubButton, StubLED, StdinPulseButton

_log = logging.getLogger(__name__)


class _AnimatingLed:
    """Presents `LEDDriver` while a `LedAnimator` owns the `PiLED`."""

    def __init__(self, animator: LedAnimator) -> None:
        self._animator = animator

    def set_colour_and_pattern(
        self,
        red: int,
        green: int,
        blue: int,
        pattern: LedPattern,
    ) -> None:
        self._animator.set_colour_and_pattern(red, green, blue, pattern)

    def close(self) -> None:
        pass


def _hal_mode() -> str:
    raw = os.environ.get("EARSHOT_HAL", "auto").strip().lower()
    if raw in ("pi", "stub", "auto"):
        return raw
    _log.warning("unknown EARSHOT_HAL=%r, using auto", raw)
    return "auto"


def _stdin_ok() -> bool:
    import sys

    return sys.stdin.isatty()


def create_hal(cfg: AppConfig) -> Hal:
    mode = _hal_mode()
    if mode == "stub":
        return _stub_hal(cfg)
    if mode == "pi":
        return _pi_hal(cfg)
    try:
        return _pi_hal(cfg)
    except Exception:
        _log.exception("Pi HAL failed; falling back to stub hardware")
        return _stub_hal(cfg)


def _stub_hal(cfg: AppConfig) -> Hal:
    led = StubLED()
    button: ButtonDriver = StdinPulseButton() if _stdin_ok() else StubButton()

    def audio_factory() -> AudioCapture:
        return StubAudioCapture(cfg.audio.channels, cfg.audio.sample_rate)

    def on_close() -> None:
        led.close()
        button.close()

    return Hal(
        led=led,
        button=button,
        pi_led=None,
        animator=None,
        _audio_factory=audio_factory,
        _on_close=on_close,
    )


def _pi_hal(cfg: AppConfig) -> Hal:
    pi_led = PiLED()
    animator = LedAnimator(pi_led)
    animator.start()
    led: LEDDriver = _AnimatingLed(animator)
    button = PiButton()
    device_index = cfg.audio.input_device_index
    alsa_pcm = cfg.audio.alsa_pcm

    def audio_factory() -> AudioCapture:
        if alsa_pcm:
            _log.info("using ALSA capture device %r (arecord)", alsa_pcm)
            return PiAlsaCapture(alsa_pcm, cfg.audio.sample_rate, cfg.audio.channels)
        return PiAudioCapture(cfg.audio.sample_rate, cfg.audio.channels, device_index)

    def on_close() -> None:
        animator.close()
        button.close()

    return Hal(
        led=led,
        button=button,
        pi_led=pi_led,
        animator=animator,
        _audio_factory=audio_factory,
        _on_close=on_close,
    )


__all__ = [
    "AudioCapture",
    "ButtonDriver",
    "Hal",
    "LEDDriver",
    "LedAnimator",
    "LedPattern",
    "create_hal",
]
