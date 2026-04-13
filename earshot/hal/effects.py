"""Short LED sequences (double-flash green, encode failure blink)."""

from __future__ import annotations

import time

from earshot.hal.bundle import Hal
from earshot.hal.protocols import LedPattern


def flash_double_green(hal: Hal, *, step_s: float = 0.12) -> None:
    """FR-2: double-flash green after discard below minimum duration."""
    if hal.pi_led is not None:
        # ReSpeaker: use PiLED for precise hardware timing
        hal.pi_led.set_target_rgb(0, 255, 0)
        for _ in range(2):
            hal.pi_led.render_scaled(1.0)
            time.sleep(step_s)
            hal.pi_led.render_scaled(0.0)
            time.sleep(step_s)
    else:
        # Drive via LEDDriver interface (stub mode)
        for _ in range(2):
            hal.led.set_colour_and_pattern(0, 255, 0, LedPattern.SOLID)
            time.sleep(step_s)
            hal.led.set_colour_and_pattern(0, 0, 0, LedPattern.OFF)
            time.sleep(step_s)
    hal.led.set_colour_and_pattern(0, 255, 0, LedPattern.SOLID)


def flash_fast_red_three_times(hal: Hal, *, step_s: float = 0.2) -> None:
    """FR-3: fast red blink ×3 on encoding failure."""
    if hal.pi_led is not None:
        hal.pi_led.set_target_rgb(255, 0, 0)
        for _ in range(3):
            hal.pi_led.render_scaled(1.0)
            time.sleep(step_s)
            hal.pi_led.render_scaled(0.0)
            time.sleep(step_s)
    else:
        for _ in range(3):
            hal.led.set_colour_and_pattern(255, 0, 0, LedPattern.SOLID)
            time.sleep(step_s)
            hal.led.set_colour_and_pattern(0, 0, 0, LedPattern.OFF)
            time.sleep(step_s)


def flash_single_blue(hal: Hal, *, step_s: float = 0.3) -> None:
    """FR-11: single blue flash on USB transfer complete."""
    if hal.pi_led is not None:
        hal.pi_led.set_target_rgb(0, 0, 255)
        hal.pi_led.render_scaled(1.0)
        time.sleep(step_s)
        hal.pi_led.render_scaled(0.0)
        time.sleep(step_s)
    else:
        hal.led.set_colour_and_pattern(0, 0, 255, LedPattern.SOLID)
        time.sleep(step_s)
        hal.led.set_colour_and_pattern(0, 0, 0, LedPattern.OFF)
        time.sleep(step_s)
