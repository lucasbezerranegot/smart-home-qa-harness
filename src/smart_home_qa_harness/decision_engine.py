from enum import Enum
from datetime import time

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
    current_time: time,
) -> WindowAction:
    """
    Determine the appropriate window action based on the outside temperature, inside temperature, and current time.
    :param outside_temperature: The current outside temperature in degrees Celsius.
    :param inside_temperature: The current inside temperature in degrees Celsius.
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

    if not isinstance(current_time, time):
        raise DecisionEngineError(
            code="INVALID_INPUT",
            message="Invalid current time value received.",
            retryable=False,
        )

    # Determine if it's evening (between 18:00 and 23:00) or daytime (between 6:00 and 11:00)
    is_evening = time(18, 0) <= current_time <= time(23, 0)
    is_daytime = time(6, 0) <= current_time <= time(11, 0)

    # Decision logic for window actions
    if is_evening:
        if outside_temperature < inside_temperature:
            return WindowAction.OPEN_WINDOWS
        else:
            # It's expected that the windows are at some point closed during the daytime, so we can return NO_ACTION here.
            return WindowAction.NO_ACTION
    elif is_daytime:
        if outside_temperature >= inside_temperature or outside_temperature >= 24:
            return WindowAction.CLOSE_WINDOWS
        else:
            # It's expected that the windows are at some point opened during the nighttime, so we can return NO_ACTION here.
            return WindowAction.NO_ACTION

    # If it's neither nighttime nor daytime, we can return NO_ACTION as a default.
    return WindowAction.NO_ACTION
