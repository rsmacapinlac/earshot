"""Short LED sequences (double-flash green, processing failure blink)."""

from __future__ import annotations

import time

from earshot.hal.bundle import Hal
from earshot.hal.protocols import LedPattern


def flash_double_green(hal: Hal, *, step_s: float = 0.12) -> None:
    """FR-2: double-flash green after discard below minimum duration."""
    if hal.pi_led is None:
        return
    hal.pi_led.set_target_rgb(0, 255, 0)
    for _ in range(2):
        hal.pi_led.render_scaled(1.0)
        time.sleep(step_s)
        hal.pi_led.render_scaled(0.0)
        time.sleep(step_s)
    hal.led.set_colour_and_pattern(0, 255, 0, LedPattern.SOLID)


def flash_fast_red_three_times(hal: Hal, *, step_s: float = 0.2) -> None:
    """FR-5c / FR-3: fast red blink ×3."""
    if hal.pi_led is None:
        return
    hal.pi_led.set_target_rgb(255, 0, 0)
    for _ in range(3):
        hal.pi_led.render_scaled(1.0)
        time.sleep(step_s)
        hal.pi_led.render_scaled(0.0)
        time.sleep(step_s)
