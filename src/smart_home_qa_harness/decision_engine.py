from enum import Enum
from datetime import time


SUMMER_COMFORT_TEMPERATURE = 24.0
HUMIDITY_THRESHOLD = 60.0


class WindowAction(Enum):
    OPEN_WINDOWS = "OPEN_WINDOWS"
    CLOSE_WINDOWS = "CLOSE_WINDOWS"
    NO_ACTION = "NO_ACTION"

class DecisionEngineError(Exception):
    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable

def decide_window_action(
    outside_temperature: float,
    inside_temperature: float,
    daily_max_temperature: float,
    relative_humidity: float,
    current_time: time,
) -> WindowAction:
    """
    Determine the appropriate window action based on the outside temperature, inside temperature, and current time.
    :param outside_temperature: The current outside temperature in degrees Celsius.
    :param inside_temperature: The current inside temperature in degrees Celsius.
    :param daily_max_temperature: The maximum temperature for the day in degrees Celsius.
    :param relative_humidity: The current relative humidity as a percentage.
    :param current_time: The current time as a datetime.time object.
    :return: A WindowAction enum value indicating the recommended action for the windows.
    """

    # Validate input types
    if isinstance(outside_temperature, bool) or not isinstance(outside_temperature, (float, int)):
        raise DecisionEngineError(
            code="INVALID_INPUT",
            message="Invalid outside temperature value received.",
            retryable=False,
        )

    if isinstance(inside_temperature, bool) or not isinstance(inside_temperature, (float, int)):
        raise DecisionEngineError(
            code="INVALID_INPUT",
            message="Invalid inside temperature value received.",
            retryable=False,
        )

    if (
        isinstance(daily_max_temperature, bool)
        or not isinstance(daily_max_temperature, (float, int))
    ):
        raise DecisionEngineError(
            code="INVALID_INPUT",
            message="Invalid daily max temperature value received.",
            retryable=False,
        )

    if (
        isinstance(relative_humidity, bool)
        or not isinstance(relative_humidity, (float, int))
        or not 0 <= relative_humidity <= 100
    ):
        raise DecisionEngineError(
            code="INVALID_INPUT",
            message="Invalid relative humidity value received.",
            retryable=False,
        )

    if not isinstance(current_time, time):
        raise DecisionEngineError(
            code="INVALID_INPUT",
            message="Invalid current time value received.",
            retryable=False,
        )

    # Actions are allowed only during the configured ventilation periods.
    is_evening = time(18, 0) <= current_time <= time(23, 0)
    is_daytime = time(6, 0) <= current_time <= time(11, 0)

    if not is_evening and not is_daytime:
        return WindowAction.NO_ACTION

    is_warm_day = daily_max_temperature >= SUMMER_COMFORT_TEMPERATURE

    # On cool days, humidity replaces temperature as the ventilation trigger.
    if not is_warm_day:
        if relative_humidity >= HUMIDITY_THRESHOLD:
            return WindowAction.OPEN_WINDOWS

        return WindowAction.NO_ACTION

    # On warm days, preserve the summer cooling behavior.
    if is_evening:
        if (
            outside_temperature < inside_temperature
            and inside_temperature > SUMMER_COMFORT_TEMPERATURE
        ):
            return WindowAction.OPEN_WINDOWS

        return WindowAction.NO_ACTION

    if is_daytime:
        if outside_temperature >= inside_temperature or outside_temperature >= 24:
            return WindowAction.CLOSE_WINDOWS

        return WindowAction.NO_ACTION

    return WindowAction.NO_ACTION
