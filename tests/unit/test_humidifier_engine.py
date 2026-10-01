from datetime import time

import pytest

from smart_home_qa_harness.humidifier_engine import (
    HumidifierDecisionError,
    decide_humidifier_state,
    is_humidification_period,
)
from smart_home_qa_harness.humidifier_provider import HumidifierState


@pytest.mark.parametrize(
    "current_time",
    [time(11, 30), time(13, 59), time(19), time(23, 59), time(0), time(7, 59)],
)
def test_sleep_period_boundaries_are_active(current_time):
    assert is_humidification_period(current_time) is True


@pytest.mark.parametrize(
    "current_time",
    [time(8), time(11, 29), time(14), time(18, 59)],
)
def test_outside_sleep_period_is_inactive(current_time):
    assert is_humidification_period(current_time) is False


def test_turns_on_below_45_percent_during_sleep_period():
    assert decide_humidifier_state(44.9, HumidifierState.OFF, time(20)) is HumidifierState.ON


def test_turns_off_at_50_percent():
    assert decide_humidifier_state(50, HumidifierState.ON, time(20)) is HumidifierState.OFF


@pytest.mark.parametrize("humidity", [45, 47.5, 49.9])
def test_hysteresis_keeps_previous_state(humidity):
    assert decide_humidifier_state(humidity, HumidifierState.ON, time(20)) is HumidifierState.ON
    assert decide_humidifier_state(humidity, HumidifierState.OFF, time(20)) is HumidifierState.OFF


def test_outside_schedule_forces_off_even_when_dry():
    assert decide_humidifier_state(30, HumidifierState.ON, time(10)) is HumidifierState.OFF


@pytest.mark.parametrize("humidity", [None, True, float("nan"), -1, 101])
def test_invalid_or_missing_humidity_fails_safe_to_off(humidity):
    assert decide_humidifier_state(humidity, HumidifierState.ON, time(20)) is HumidifierState.OFF


@pytest.mark.parametrize(
    "arguments",
    [
        {"relative_humidity": 40, "previous_state": "OFF", "current_time": time(20)},
        {"relative_humidity": 40, "previous_state": HumidifierState.OFF, "current_time": "20:00"},
        {
            "relative_humidity": 40,
            "previous_state": HumidifierState.OFF,
            "current_time": time(20),
            "on_below": 50,
            "off_at": 45,
        },
    ],
)
def test_rejects_invalid_rule_inputs(arguments):
    with pytest.raises(HumidifierDecisionError):
        decide_humidifier_state(**arguments)
