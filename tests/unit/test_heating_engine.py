import pytest

from smart_home_qa_harness.heating_engine import (
    HeatingEngineError,
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


@pytest.mark.parametrize("meter_id", ["", "   ", None, 123])
def test_rejects_invalid_meter_id(meter_id):
    with pytest.raises(HeatingEngineError) as captured:
        MeterReading(
            meter_id=meter_id,
            temperature=20.0,
            status=MeterReadingStatus.VALID,
        )

    assert captured.value.code == "INVALID_METER_ID"
    assert captured.value.retryable is False


@pytest.mark.parametrize("temperature", [None, True, "22", float("nan"), float("inf")])
def test_rejects_invalid_temperature_for_valid_reading(temperature):
    with pytest.raises(HeatingEngineError) as captured:
        MeterReading(
            meter_id="children-room-meter",
            temperature=temperature,
            status=MeterReadingStatus.VALID,
        )

    assert captured.value.code == "INVALID_METER_TEMPERATURE"


def test_rejects_invalid_reading_status():
    with pytest.raises(HeatingEngineError) as captured:
        MeterReading(
            meter_id="children-room-meter",
            temperature=20.0,
            status="VALID",
        )

    assert captured.value.code == "INVALID_READING_STATUS"


@pytest.mark.parametrize("previous_state", ["", "on", "UNKNOWN", None, 1])
def test_rejects_invalid_previous_state(previous_state):
    reading = MeterReading(
        meter_id="children-room-meter",
        temperature=20.0,
        status=MeterReadingStatus.VALID,
    )

    with pytest.raises(HeatingEngineError) as captured:
        decide_heating_state(
            reading=reading,
            previous_state=previous_state,
            target_temperature=20.0,
            hysteresis=0.5,
        )

    assert captured.value.code == "INVALID_PREVIOUS_STATE"


@pytest.mark.parametrize("target_temperature", [None, True, "20", float("nan"), float("inf")])
def test_rejects_invalid_target_temperature(target_temperature):
    reading = MeterReading(
        meter_id="children-room-meter",
        temperature=20.0,
        status=MeterReadingStatus.VALID,
    )

    with pytest.raises(HeatingEngineError) as captured:
        decide_heating_state(
            reading=reading,
            previous_state="ON",
            target_temperature=target_temperature,
            hysteresis=0.5,
        )

    assert captured.value.code == "INVALID_TARGET_TEMPERATURE"


@pytest.mark.parametrize("hysteresis", [-0.1, None, True, "0.5", float("nan"), float("inf")])
def test_rejects_invalid_hysteresis(hysteresis):
    reading = MeterReading(
        meter_id="children-room-meter",
        temperature=20.0,
        status=MeterReadingStatus.VALID,
    )

    with pytest.raises(HeatingEngineError) as captured:
        decide_heating_state(
            reading=reading,
            previous_state="ON",
            target_temperature=20.0,
            hysteresis=hysteresis,
        )

    assert captured.value.code == "INVALID_HYSTERESIS"
