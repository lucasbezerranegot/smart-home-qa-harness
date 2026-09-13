from datetime import time
import pytest

from smart_home_qa_harness.decision_engine import (
    DecisionEngineError,
    WindowAction,
    decide_window_action,
)

# Evening tests (between 18:00 and 23:00)

def test_opens_windows_when_outside_is_cooler_during_evening():
    # Arrange
    outside_temperature = 18.0
    inside_temperature = 24.5
    current_time = time(20, 0)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.OPEN_WINDOWS

def test_opens_windows_at_evening_start_boundary():
    # Arrange
    outside_temperature = 18.0
    inside_temperature = 24.5
    current_time = time(18, 0)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.OPEN_WINDOWS

def test_opens_windows_at_evening_end_boundary():
    # Arrange
    outside_temperature = 18.0
    inside_temperature = 24.5
    current_time = time(23, 0)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.OPEN_WINDOWS

def test_takes_no_action_when_outside_is_cooler_at_evening_right_before_start_boundary():
    # Arrange
    outside_temperature = 18.0
    inside_temperature = 24.0
    current_time = time(17, 59)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.NO_ACTION

def test_takes_no_action_when_outside_is_cooler_at_evening_right_after_end_boundary():
    # Arrange
    outside_temperature = 18.0
    inside_temperature = 24.0
    current_time = time(23, 1)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.NO_ACTION

def test_takes_no_action_when_outside_is_equal_to_inside_during_evening():
    # Arrange
    outside_temperature = 24.0
    inside_temperature = 24.0
    current_time = time(20, 0)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.NO_ACTION

# Daytime tests (between 6:00 and 11:00)

def test_takes_no_action_when_outside_is_cooler_during_daytime():
    # Arrange
    outside_temperature = 22.0
    inside_temperature = 23.0
    current_time = time(10, 0)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.NO_ACTION

def test_closes_windows_when_outside_is_24_during_daytime():
    # Arrange
    outside_temperature = 24.0
    inside_temperature = 24.5
    current_time = time(10, 0)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.CLOSE_WINDOWS

def test_closes_windows_at_daytime_end_boundary():
    # Arrange
    outside_temperature = 24.0
    inside_temperature = 23.0
    current_time = time(11, 0)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.CLOSE_WINDOWS

def test_closes_windows_at_daytime_start_boundary():
    # Arrange
    outside_temperature = 23.0
    inside_temperature = 22.0
    current_time = time(6, 0)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.CLOSE_WINDOWS

def test_takes_no_action_daytime_just_before_start_boundary():
    # Arrange
    outside_temperature = 23.0
    inside_temperature = 22.0
    current_time = time(5, 59)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.NO_ACTION

def test_takes_no_action_at_daytime_right_after_end_boundary():
    # Arrange
    outside_temperature = 23.0
    inside_temperature = 22.0
    current_time = time(11, 1)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.NO_ACTION

def test_closes_windows_when_outside_is_equal_to_inside_during_daytime():
    # Arrange
    outside_temperature = 24.0
    inside_temperature = 24.0
    current_time = time(10, 0)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.CLOSE_WINDOWS

def test_closes_windows_when_outside_is_warmer_during_morning():
    # Arrange
    outside_temperature = 23.0
    inside_temperature = 22.0
    current_time = time(10, 0)

    # Act
    result = decide_window_action(
        outside_temperature,
        inside_temperature,
        daily_max_temperature=27.0,
        relative_humidity=50.0,
        current_time=current_time,
    )

    # Assert
    assert result is WindowAction.CLOSE_WINDOWS

# Invalid input tests

@pytest.mark.parametrize(
    (
        "outside_temperature, inside_temperature, "
        "daily_max_temperature, relative_humidity, current_time"
    ),
    [
        (True, 22.0, 27.0, 50.0, time(10, 0)),
        (22.0, False, 27.0, 50.0, time(10, 0)),
        ("hot", 22.0, 27.0, 50.0, time(10, 0)),
        (22.0, "cold", 27.0, 50.0, time(10, 0)),
        (22.0, 22.0, True, 50.0, time(10, 0)),
        (22.0, 22.0, "warm", 50.0, time(10, 0)),
        (22.0, 22.0, 27.0, None, time(10, 0)),
        (22.0, 22.0, 27.0, True, time(10, 0)),
        (22.0, 22.0, 27.0, 101, time(10, 0)),
        (22.0, 22.0, 27.0, -1, time(10, 0)),
        (22.0, 22.0, 27.0, 50.0, "10:00"),
        (22.0, 22.0, 27.0, 50.0, 100),
    ]
)
def test_invalid_inputs_raise_decision_engine_error(
    outside_temperature,
    inside_temperature,
    daily_max_temperature,
    relative_humidity,
    current_time,
):
    with pytest.raises(DecisionEngineError) as captured:
        decide_window_action(
            outside_temperature=outside_temperature,
            inside_temperature=inside_temperature,
            daily_max_temperature=daily_max_temperature,
            relative_humidity=relative_humidity,
            current_time=current_time,
        )

    assert captured.value.code == "INVALID_INPUT"
    assert captured.value.retryable is False

@pytest.mark.parametrize(
    "current_time",
    [
        time(8, 0),
        time(20, 0),
    ],
)
def test_opens_windows_for_high_humidity_on_cool_day(current_time):
    result = decide_window_action(
        outside_temperature=10.0,
        inside_temperature=21.0,
        daily_max_temperature=18.0,
        relative_humidity=65.0,
        current_time=current_time,
    )

    assert result is WindowAction.OPEN_WINDOWS

def test_opens_windows_when_humidity_equals_threshold_on_cool_day():
    result = decide_window_action(
        outside_temperature=10.0,
        inside_temperature=21.0,
        daily_max_temperature=18.0,
        relative_humidity=60.0,
        current_time=time(8, 0),
    )

    assert result is WindowAction.OPEN_WINDOWS

def test_takes_no_action_for_low_humidity_on_cool_day():
    result = decide_window_action(
        outside_temperature=10.0,
        inside_temperature=21.0,
        daily_max_temperature=18.0,
        relative_humidity=59.9,
        current_time=time(20, 0),
    )

    assert result is WindowAction.NO_ACTION

def test_takes_no_action_for_high_humidity_outside_ventilation_periods():
    result = decide_window_action(
        outside_temperature=10.0,
        inside_temperature=21.0,
        daily_max_temperature=18.0,
        relative_humidity=70.0,
        current_time=time(14, 0),
    )

    assert result is WindowAction.NO_ACTION

def test_high_humidity_does_not_replace_temperature_rules_on_warm_day():
    result = decide_window_action(
        outside_temperature=25.0,
        inside_temperature=26.0,
        daily_max_temperature=27.0,
        relative_humidity=70.0,
        current_time=time(10, 0),
    )

    assert result is WindowAction.CLOSE_WINDOWS

def test_does_not_open_windows_below_summer_comfort_temperature():
    result = decide_window_action(
        outside_temperature=18.0,
        inside_temperature=22.0,
        daily_max_temperature=25.0,
        relative_humidity=50.0,
        current_time=time(20, 0),
    )

    assert result is WindowAction.NO_ACTION
