from pytest_bdd import given, parsers, scenarios, then, when
from datetime import time
from smart_home_qa_harness.decision_engine import decide_window_action

scenarios("../features/ventilation.feature")

@given(
    "the daily maximum temperature is 20 degrees Celsius",
    target_fixture="daily_max_temperature",
)
def daily_max_temperature():
    return 20.0

@given(
    "the relative humidity is 65 percent",
    target_fixture="relative_humidity",
)
def relative_humidity():
    return 65.0

@given(
    parsers.parse('the current time is "{time_text}"'),
    target_fixture="current_time",
)
def current_time(time_text):
    return time.fromisoformat(time_text)

@when(
    "the engine evaluates ventilation",
    target_fixture="actual_action",
)
def evaluate_ventilation(
    daily_max_temperature,
    relative_humidity,
    current_time,
):
    return decide_window_action(
        outside_temperature=18.0,
        inside_temperature=22.0,
        daily_max_temperature=daily_max_temperature,
        relative_humidity=relative_humidity,
        current_time=current_time,
    )

@then(parsers.parse('the action should be "{expected_action}"'))
def verify_action(actual_action, expected_action):
    assert actual_action.value == expected_action