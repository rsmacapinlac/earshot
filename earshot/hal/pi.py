"""Raspberry Pi hardware: ReSpeaker HAT button, APA102 LED, ALSA capture."""

from __future__ import annotations

import logging
import shutil
import subprocess

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
    def __init__(self, active_high: bool = False) -> None:
        import RPi.GPIO as GPIO  # type: ignore[import-untyped]

        self._GPIO = GPIO
        self._active_high = active_high
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        pull = GPIO.PUD_DOWN if active_high else GPIO.PUD_UP
        GPIO.setup(_BUTTON_GPIO_BCM, GPIO.IN, pull_up_down=pull)
        raw = GPIO.input(_BUTTON_GPIO_BCM)
        _log.info(
            "Button on GPIO%d (%s): initial line reads %s",
            _BUTTON_GPIO_BCM,
            "pull-down, active-high" if active_high else "pull-up, active-low",
            "HIGH — button appears pressed; release it for idle"
            if (raw == GPIO.HIGH) == active_high
            else "LOW — not pressed" if not active_high else "LOW — not pressed",
        )

    def pressed(self) -> bool:
        val = self._GPIO.input(_BUTTON_GPIO_BCM)
        return (val == self._GPIO.HIGH) if self._active_high else (val == self._GPIO.LOW)

    def close(self) -> None:
        self._GPIO.cleanup()


class PiAlsaCapture(AudioCapture):
    """Capture via ALSA `arecord` (raw PCM). Prefer `plughw:CARD,DEV` so rates are converted in ALSA."""

    def __init__(self, alsa_pcm: str, sample_rate: int, channels: int) -> None:
        self._alsa_pcm = alsa_pcm
        self._sample_rate = sample_rate
        self._channels = channels
        self._proc: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        if self._proc is not None:
            return
        if not shutil.which("arecord"):
            raise RuntimeError("arecord not found; install alsa-utils")
        cmd = [
            "arecord",
            "-D",
            self._alsa_pcm,
            "-f",
            "S16_LE",
            "-c",
            str(self._channels),
            "-r",
            str(self._sample_rate),
            "-t",
            "raw",
            "-q",
            "-",
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            bufsize=0,
        )

    def read_frames(self, num_frames: int) -> bytes:
        if self._proc is None or self._proc.stdout is None:
            raise RuntimeError("PiAlsaCapture.start() not called")
        nbytes = num_frames * self._channels * 2
        chunks: list[bytes] = []
        remaining = nbytes
        while remaining > 0:
            block = self._proc.stdout.read(remaining)
            if not block:
                code = self._proc.poll()
                raise RuntimeError(f"arecord stopped while reading (exit {code})")
            chunks.append(block)
            remaining -= len(block)
        return b"".join(chunks)

    def stop(self) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=2.0)
        if self._proc.stdout:
            try:
                self._proc.stdout.close()
            except OSError:
                pass
        self._proc = None

    def close(self) -> None:
        self.stop()


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
