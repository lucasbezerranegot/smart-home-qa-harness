"""Exercise real component wiring while keeping every HTTP request offline."""

import json
from datetime import date, time
from unittest.mock import Mock

import pytest
import responses

from smart_home_qa_harness.decision_engine import WindowAction
from smart_home_qa_harness.inside_environment_client import IndoorEnvironmentData
from smart_home_qa_harness.notification_store import FileNotificationStore
from smart_home_qa_harness.orchestrator import run_environment_control
from smart_home_qa_harness.weather_client import BASE_URL
from smart_home_qa_harness.webhook_notifier import VOICE_MONKEY_TRIGGER_URL


def register_weather(outside, daily_max):
    """Supply a provider-shaped response; the production parser still runs."""
    responses.add(
        responses.GET,
        BASE_URL,
        json={
            "current": {"temperature_2m": outside, "time": "2026-09-13T08:00"},
            "daily": {"temperature_2m_max": [daily_max]},
        },
        status=200,
    )


def control_arguments(state_path, inside, humidity):
    """Inject indoor readings and a real temporary-file reservation adapter."""
    return {
        "latitude": 48.13,
        "longitude": 11.57,
        "inside_environment_provider": Mock(
            return_value=IndoorEnvironmentData(
                temperature=inside,
                relative_humidity=humidity,
                retrieved_at="2026-09-13T06:00:00+00:00",
                source="switchbot:fake-meter",
            )
        ),
        "current_date": date(2026, 9, 13),
        "reserve_notification": FileNotificationStore(state_path).reserve,
        "api_token": "fake-token",
        "open_device_id": "fake-open-device",
        "close_device_id": "fake-close-device",
    }


@responses.activate
@pytest.mark.parametrize(
    "outside, inside, daily_max, humidity, current_time, expected_action, period",
    [
        (18.0, 25.0, 27.0, 50.0, time(20), WindowAction.OPEN_WINDOWS, "evening"),
        (18.0, 24.0, 27.0, 50.0, time(20), WindowAction.NO_ACTION, None),
        (23.0, 22.0, 27.0, 50.0, time(8), WindowAction.CLOSE_WINDOWS, "morning"),
        (23.0, 25.0, 27.0, 50.0, time(8), WindowAction.NO_ACTION, None),
        (10.0, 21.0, 23.9, 60.0, time(8), WindowAction.OPEN_WINDOWS, "morning"),
        (10.0, 21.0, 18.0, 65.0, time(20), WindowAction.OPEN_WINDOWS, "evening"),
        (10.0, 21.0, 18.0, 59.9, time(20), WindowAction.NO_ACTION, None),
        (10.0, 21.0, 18.0, 70.0, time(14), WindowAction.NO_ACTION, None),
        (10.0, 21.0, 24.0, 70.0, time(8), WindowAction.NO_ACTION, None),
    ],
)
def test_real_rules_reach_expected_webhook_and_state(
    tmp_path, outside, inside, daily_max, humidity, current_time, expected_action, period
):
    # Arrange: HTTP is mocked, but no application component is patched.
    register_weather(outside, daily_max)
    if period is not None:
        responses.add(responses.POST, VOICE_MONKEY_TRIGGER_URL, status=200)
    state_path = tmp_path / "notifications.json"

    # Act: current_time is injected so this test never depends on the real clock.
    result = run_environment_control(
        **control_arguments(state_path, inside, humidity), current_time=current_time
    )

    # Assert the recommendation, side effects and exact selected Alexa device.
    assert result.action is expected_action
    assert result.error_code is None
    assert result.webhook_sent is (period is not None)
    assert result.notification_suppressed is False
    if period is None:
        assert len(responses.calls) == 1  # Only the weather GET; no webhook.
        assert not state_path.exists()  # NO_ACTION must not consume a period.
    else:
        assert len(responses.calls) == 2
        assert json.loads(responses.calls[1].request.body) == {
            "token": "fake-token",
            "device": (
                "fake-open-device"
                if expected_action is WindowAction.OPEN_WINDOWS
                else "fake-close-device"
            ),
        }
        assert json.loads(state_path.read_text()) == [f"2026-09-13:{period}"]


@responses.activate
def test_cool_day_can_notify_once_in_each_period_across_store_instances(tmp_path):
    """A new process/store must suppress repeats without suppressing the evening."""
    register_weather(10.0, 18.0)
    responses.add(responses.POST, VOICE_MONKEY_TRIGGER_URL, status=200)
    state_path = tmp_path / "notifications.json"

    results = []
    for current_time in (time(8), time(8, 30), time(20)):
        # Recreate the adapter to demonstrate persisted state, not in-memory state.
        results.append(run_environment_control(
            **control_arguments(state_path, 21.0, 65.0), current_time=current_time
        ))

    assert [result.webhook_sent for result in results] == [True, False, True]
    assert [result.notification_suppressed for result in results] == [False, True, False]
    assert all(result.action is WindowAction.OPEN_WINDOWS for result in results)
    assert len([call for call in responses.calls if call.request.method == "POST"]) == 2
    assert json.loads(state_path.read_text()) == [
        "2026-09-13:evening", "2026-09-13:morning"
    ]


@responses.activate
def test_missing_daily_forecast_stops_real_workflow_before_webhook(tmp_path):
    responses.add(
        responses.GET, BASE_URL,
        json={"current": {"temperature_2m": 10.0, "time": "2026-09-13T08:00"}},
        status=200,
    )
    state_path = tmp_path / "notifications.json"
    arguments = control_arguments(state_path, 21.0, 65.0)

    result = run_environment_control(**arguments, current_time=time(8))

    assert result.error_code == "INVALID_PAYLOAD"
    assert result.action is WindowAction.NO_ACTION
    assert result.webhook_sent is False
    arguments["inside_environment_provider"].assert_not_called()
    assert len(responses.calls) == 1
    assert not state_path.exists()
