import pytest

from smart_home_qa_harness.heating_control import (
    HeatingConfiguration,
    HeatingConfigurationError,
    decide_relay_state,
)
from smart_home_qa_harness.heating_engine import (
    MeterReading,
    MeterReadingStatus,
)


def configuration(
    target_temperature=20.0,
    hysteresis=0.5,
):
    return HeatingConfiguration(
        relay_id="children-room-relay",
        meter_id="children-room-meter",
        target_temperature=target_temperature,
        hysteresis=hysteresis,
    )


def reading(meter_id, temperature, status=MeterReadingStatus.VALID):
    return MeterReading(
        meter_id=meter_id,
        temperature=temperature,
        status=status,
    )


@pytest.mark.parametrize("associated_reading_first", [True, False])
def test_uses_only_the_associated_meter_regardless_of_reading_order(
    associated_reading_first,
):
    associated = reading("children-room-meter", 19.0)
    unrelated = reading("another-meter", 25.0)
    readings = (
        [associated, unrelated]
        if associated_reading_first
        else [unrelated, associated]
    )

    result = decide_relay_state(
        configuration=configuration(),
        readings=readings,
        previous_state="OFF",
    )

    assert result == "ON"


def test_turns_heating_off_when_associated_meter_is_missing():
    result = decide_relay_state(
        configuration=configuration(),
        readings=[reading("another-meter", 18.0)],
        previous_state="ON",
    )

    assert result == "OFF"


def test_does_not_fall_back_to_another_meter_when_associated_reading_is_invalid():
    result = decide_relay_state(
        configuration=configuration(),
        readings=[
            reading(
                "children-room-meter",
                None,
                MeterReadingStatus.INVALID,
            ),
            reading("another-meter", 18.0),
        ],
        previous_state="ON",
    )

    assert result == "OFF"


def test_uses_target_temperature_from_configuration():
    result = decide_relay_state(
        configuration=configuration(target_temperature=18.0),
        readings=[reading("children-room-meter", 19.0)],
        previous_state="ON",
    )

    assert result == "OFF"


def test_uses_hysteresis_from_configuration():
    result = decide_relay_state(
        configuration=configuration(hysteresis=2.0),
        readings=[reading("children-room-meter", 18.5)],
        previous_state="OFF",
    )

    assert result == "OFF"


def test_turns_children_room_relay_off_at_current_temperature():
    result = decide_relay_state(
        configuration=configuration(),
        readings=[reading("children-room-meter", 22.0)],
        previous_state="ON",
    )

    assert result == "OFF"


@pytest.mark.parametrize("relay_id", ["", "   ", None, 123])
def test_rejects_invalid_relay_id(relay_id):
    with pytest.raises(HeatingConfigurationError) as captured:
        HeatingConfiguration(
            relay_id=relay_id,
            meter_id="children-room-meter",
            target_temperature=20.0,
            hysteresis=0.5,
        )

    assert captured.value.code == "INVALID_RELAY_ID"
    assert captured.value.retryable is False


@pytest.mark.parametrize("meter_id", ["", "   ", None, 123])
def test_rejects_invalid_configured_meter_id(meter_id):
    with pytest.raises(HeatingConfigurationError) as captured:
        HeatingConfiguration(
            relay_id="children-room-relay",
            meter_id=meter_id,
            target_temperature=20.0,
            hysteresis=0.5,
        )

    assert captured.value.code == "INVALID_METER_ID"


@pytest.mark.parametrize("target_temperature", [None, True, "20", float("nan"), float("inf")])
def test_rejects_invalid_configured_target_temperature(target_temperature):
    with pytest.raises(HeatingConfigurationError) as captured:
        HeatingConfiguration(
            relay_id="children-room-relay",
            meter_id="children-room-meter",
            target_temperature=target_temperature,
            hysteresis=0.5,
        )

    assert captured.value.code == "INVALID_TARGET_TEMPERATURE"


@pytest.mark.parametrize("hysteresis", [-0.1, None, True, "0.5", float("nan"), float("inf")])
def test_rejects_invalid_configured_hysteresis(hysteresis):
    with pytest.raises(HeatingConfigurationError) as captured:
        HeatingConfiguration(
            relay_id="children-room-relay",
            meter_id="children-room-meter",
            target_temperature=20.0,
            hysteresis=hysteresis,
        )

    assert captured.value.code == "INVALID_HYSTERESIS"
