"""Raspberry Pi hardware: ReSpeaker HAT button, APA102 LED, ALSA capture."""

from __future__ import annotations

import logging

import pyaudio

from earshot.hal.protocols import AudioCapture, ButtonDriver, LEDDriver, LedPattern

_log = logging.getLogger(__name__)

_BUTTON_GPIO_BCM = 17
_NUM_APA102 = 3
_APA102_PIXEL = 0


class PiLED(LEDDriver):
    """First APA102 on the ReSpeaker HAT; other pixels cleared."""

    def __init__(self) -> None:
        from apa102_pi.driver import apa102

        self._strip = apa102.APA102(
            num_led=_NUM_APA102,
            order="rgb",
            bus_method="spi",
            spi_bus=0,
            global_brightness=10,
        )
        self._red = 0
        self._green = 0
        self._blue = 0
        self._strip.clear_strip()

    def set_target_rgb(self, red: int, green: int, blue: int) -> None:
        self._red = max(0, min(255, red))
        self._green = max(0, min(255, green))
        self._blue = max(0, min(255, blue))

    def render_scaled(self, brightness: float) -> None:
        brightness = max(0.0, min(1.0, brightness))
        r = int(self._red * brightness)
        g = int(self._green * brightness)
        b = int(self._blue * brightness)
        for i in range(_NUM_APA102):
            if i == _APA102_PIXEL:
                self._strip.set_pixel(i, r, g, b)
            else:
                self._strip.set_pixel(i, 0, 0, 0)
        self._strip.show()

    def set_colour_and_pattern(
        self,
        red: int,
        green: int,
        blue: int,
        pattern: LedPattern,
    ) -> None:
        self.set_target_rgb(red, green, blue)
        if pattern == LedPattern.OFF:
            self.render_scaled(0.0)
        else:
            self.render_scaled(1.0)

    def close(self) -> None:
        try:
            self._strip.cleanup()
        except OSError as exc:
            _log.debug("APA102 cleanup: %s", exc)


class PiButton(ButtonDriver):
    def __init__(self) -> None:
        import RPi.GPIO as GPIO  # type: ignore[import-untyped]

        self._GPIO = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(_BUTTON_GPIO_BCM, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def pressed(self) -> bool:
        return self._GPIO.input(_BUTTON_GPIO_BCM) == self._GPIO.LOW

    def close(self) -> None:
        self._GPIO.cleanup()


class PiAudioCapture(AudioCapture):
    def __init__(self, sample_rate: int, channels: int, device_index: int | None = None) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._device_index = device_index
        self._pa: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None

    def start(self) -> None:
        if self._stream is not None:
            return
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=self._sample_rate,
            input=True,
            frames_per_buffer=1024,
            input_device_index=self._device_index,
        )

    def read_frames(self, num_frames: int) -> bytes:
        if self._stream is None:
            raise RuntimeError("PiAudioCapture.start() not called")
        return self._stream.read(num_frames, exception_on_overflow=False)

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None

    def close(self) -> None:
        self.stop()
