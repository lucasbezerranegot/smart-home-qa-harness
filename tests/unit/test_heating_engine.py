import pytest

from smart_home_qa_harness.heating_engine import (
    MeterReading,
    MeterReadingStatus,
    decide_heating_state,
)


@pytest.mark.parametrize(
    ("temperature", "previous_state", "expected_state"),
    [
        (19.4, "OFF", "ON"),
        (19.5, "OFF", "ON"),
        (19.6, "OFF", "OFF"),
        (19.6, "ON", "ON"),
        (19.9, "OFF", "OFF"),
        (19.9, "ON", "ON"),
        (20.0, "ON", "OFF"),
        (22.0, "ON", "OFF"),
    ],
)
def test_decides_heating_state_with_hysteresis(
    temperature,
    previous_state,
    expected_state,
):
    reading = MeterReading(
        meter_id="children-room-meter",
        temperature=temperature,
        status=MeterReadingStatus.VALID,
    )

    result = decide_heating_state(
        reading=reading,
        previous_state=previous_state,
        target_temperature=20.0,
        hysteresis=0.5,
    )

    assert result == expected_state


@pytest.mark.parametrize(
    "status",
    [
        MeterReadingStatus.MISSING,
        MeterReadingStatus.INVALID,
        MeterReadingStatus.STALE,
    ],
)
def test_turns_heating_off_for_unsafe_reading_status(status):
    reading = MeterReading(
        meter_id="children-room-meter",
        temperature=None,
        status=status,
    )

    result = decide_heating_state(
        reading=reading,
        previous_state="ON",
        target_temperature=20.0,
        hysteresis=0.5,
    )

    assert result == "OFF"


def test_turns_heating_off_when_valid_reading_has_no_temperature():
    reading = MeterReading(
        meter_id="children-room-meter",
        temperature=None,
        status=MeterReadingStatus.VALID,
    )

    result = decide_heating_state(
        reading=reading,
        previous_state="ON",
        target_temperature=20.0,
        hysteresis=0.5,
    )

    assert result == "OFF"
