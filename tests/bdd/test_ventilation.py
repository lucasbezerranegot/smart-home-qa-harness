from pytest_bdd import given, parsers, scenarios, then, when
from datetime import time
from smart_home_qa_harness.decision_engine import decide_window_action

scenarios("../features/ventilation.feature")

@given(
    parsers.parse(
        "the daily maximum temperature is {temperature:g} degrees Celsius"
    ),
    target_fixture="daily_max_temperature",
)
def daily_max_temperature(temperature):
    return temperature

@given(
    parsers.parse("the relative humidity is {humidity:g} percent"),
    target_fixture="relative_humidity",
)
def relative_humidity(humidity):
    return humidity

@given(
    parsers.parse('the current time is "{time_text}"'),
    target_fixture="current_time",
)
def current_time(time_text):
    return time.fromisoformat(time_text)

@given(
    parsers.parse(
        "the outside temperature is {outside_temperature:g} degrees Celsius"
    ),
    target_fixture="outside_temperature",
)
def outside_temperature(outside_temperature):
    return outside_temperature

@given(
    parsers.parse(
        "the inside temperature is {inside_temperature:g} degrees Celsius"
    ),
    target_fixture="inside_temperature",
)
def inside_temperature(inside_temperature):
    return inside_temperature

@when(
    "the engine evaluates ventilation",
    target_fixture="actual_action",
)
def evaluate_ventilation(
    daily_max_temperature,
    relative_humidity,
    current_time,
    outside_temperature,
    inside_temperature,
):
    return decide_window_action(
        outside_temperature=outside_temperature,
        inside_temperature=inside_temperature,
        daily_max_temperature=daily_max_temperature,
        relative_humidity=relative_humidity,
        current_time=current_time,
    )

@then(parsers.parse('the action should be "{expected_action}"'))
def verify_action(actual_action, expected_action):
    assert actual_action.value == expected_action