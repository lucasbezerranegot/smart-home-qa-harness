"""Pure schedule and hysteresis rules for plug-controlled humidifiers."""

from datetime import time
import math

from smart_home_qa_harness.switchbot_plug_client import PlugState


HUMIDIFIER_ON_BELOW = 45.0
HUMIDIFIER_OFF_AT = 50.0


class HumidifierDecisionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = False


def is_humidification_period(current_time: time) -> bool:
    """Return whether children are expected to be sleeping."""

    if not isinstance(current_time, time):
        raise HumidifierDecisionError(
            "INVALID_HUMIDIFIER_INPUT",
            "Current time must be a datetime.time value.",
        )

    nap = time(11, 30) <= current_time < time(14, 0)
    night = current_time >= time(19, 0) or current_time < time(8, 0)
    return nap or night


def decide_humidifier_state(
    relative_humidity: float | None,
    previous_state: PlugState,
    current_time: time,
    on_below: float = HUMIDIFIER_ON_BELOW,
    off_at: float = HUMIDIFIER_OFF_AT,
) -> PlugState:
    """Choose a safe desired state using schedule and humidity hysteresis."""

    if not isinstance(previous_state, PlugState):
        raise HumidifierDecisionError(
            "INVALID_HUMIDIFIER_INPUT",
            "Previous state must be a PlugState value.",
        )
    if not _valid_threshold(on_below) or not _valid_threshold(off_at):
        raise HumidifierDecisionError(
            "INVALID_HUMIDIFIER_INPUT",
            "Humidity thresholds must be finite values from 0 to 100.",
        )
    if on_below >= off_at:
        raise HumidifierDecisionError(
            "INVALID_HUMIDIFIER_INPUT",
            "The turn-on threshold must be below the turn-off threshold.",
        )

    # A missing or invalid measurement must never leave a humidifier running.
    if not _valid_threshold(relative_humidity):
        return PlugState.OFF
    if not is_humidification_period(current_time):
        return PlugState.OFF
    if relative_humidity < on_below:
        return PlugState.ON
    if relative_humidity >= off_at:
        return PlugState.OFF
    return previous_state


def _valid_threshold(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and 0 <= value <= 100
    )
