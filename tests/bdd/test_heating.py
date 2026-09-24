from pytest_bdd import given, parsers, scenarios, then, when

from smart_home_qa_harness.heating_control import (
    HeatingConfiguration,
    decide_relay_state,
)
from smart_home_qa_harness.heating_engine import (
    MeterReading,
    MeterReadingStatus,
    decide_heating_state,
)

scenarios("../features/heating.feature")


# Steps used by the heating engine scenarios


@given(
    "a heating relay associated with a Meter",
    target_fixture="relay_meter_pair",
)
def relay_meter_pair():
    return {
        "relay_id": "children-room-relay",
        "meter_id": "children-room-meter",
    }


@given(
    parsers.parse('the relay is "{state}"'),
    target_fixture="previous_state",
)
def previous_state(state):
    assert state in {"ON", "OFF"}
    return state


@given(
    parsers.parse(
        "the associated Meter has a valid temperature of "
        "{temperature:g} degrees Celsius"
    ),
    target_fixture="meter_reading",
)
def valid_meter_reading(relay_meter_pair, temperature):
    return MeterReading(
        meter_id=relay_meter_pair["meter_id"],
        temperature=temperature,
        status=MeterReadingStatus.VALID,
    )


@given(
    parsers.parse('the associated Meter reading is "{reading_status}"'),
    target_fixture="meter_reading",
)
def unavailable_meter_reading(relay_meter_pair, reading_status):
    return MeterReading(
        meter_id=relay_meter_pair["meter_id"],
        temperature=None,
        status=MeterReadingStatus(reading_status),
    )


@when(
    "the heating engine evaluates the Meter reading",
    target_fixture="actual_state",
)
def evaluate_heating(relay_meter_pair, meter_reading, previous_state):
    assert meter_reading.meter_id == relay_meter_pair["meter_id"]

    return decide_heating_state(
        reading=meter_reading,
        previous_state=previous_state,
        target_temperature=20.0,
        hysteresis=0.5,
    )


# Steps used by the Meter association scenario


@given(
    "the children room relay is associated with the children room Meter",
    target_fixture="heating_configuration",
)
def children_room_configuration():
    return HeatingConfiguration(
        relay_id="children-room-relay",
        channel=2,
        meter_id="children-room-meter",
        target_temperature=20.0,
        hysteresis=0.5,
    )


@given(
    parsers.parse(
        "the children room Meter reads {temperature:g} degrees Celsius"
    ),
    target_fixture="available_readings",
)
def children_room_reading(temperature):
    return [
        MeterReading(
            meter_id="children-room-meter",
            temperature=temperature,
            status=MeterReadingStatus.VALID,
        )
    ]


@given(parsers.parse("another Meter reads {temperature:g} degrees Celsius"))
def another_meter_reading(available_readings, temperature):
    available_readings.append(
        MeterReading(
            meter_id="another-meter",
            temperature=temperature,
            status=MeterReadingStatus.VALID,
        )
    )


@when(
    "the heating control evaluates the available Meter readings",
    target_fixture="actual_state",
)
def evaluate_available_readings(
    heating_configuration,
    available_readings,
    previous_state,
):
    return decide_relay_state(
        configuration=heating_configuration,
        readings=available_readings,
        previous_state=previous_state,
    )


# Shared assertion


@then(parsers.parse('the relay should be "{expected_state}"'))
def verify_heating_state(actual_state, expected_state):
    assert actual_state == expected_state
