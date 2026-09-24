from pytest_bdd import given, parsers, scenarios, then, when

from smart_home_qa_harness.heating_engine import (
    MeterReading,
    MeterReadingStatus,
    decide_heating_state,
)

scenarios("../features/heating.feature")


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


@then(parsers.parse('the relay should be "{expected_state}"'))
def verify_heating_state(actual_state, expected_state):
    assert actual_state == expected_state