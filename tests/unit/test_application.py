"""Tests for configuration parsing and application component wiring.

``patch`` replaces real dependencies only inside the application module.
``call_args.kwargs`` lets the test inspect the named arguments passed to a
mock. The SwitchBot provider is called manually in the wiring test because the
orchestrator itself is mocked and therefore cannot call that provider.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from smart_home_qa_harness.application import (
    ApplicationConfig,
    ConfigurationError,
    load_application_config,
    run_application,
)
from smart_home_qa_harness.decision_engine import WindowAction
from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentData,
)
from smart_home_qa_harness.orchestrator import OrchestrationResult

VALID_ENVIRON = {
    "WEATHER_LATITUDE": "48.13",
    "WEATHER_LONGITUDE": "11.57",
    "SWITCHBOT_TOKEN": "fake-switchbot-token",
    "SWITCHBOT_SECRET": "fake-switchbot-secret",
    "SWITCHBOT_DEVICE_ID": "AABBCCDDEEFF",
    "VOICE_MONKEY_API_TOKEN": "fake-voice-monkey-token",
    "VOICE_MONKEY_OPEN_DEVICE_ID": "fake-open-device",
    "VOICE_MONKEY_CLOSE_DEVICE_ID": "fake-close-device",
}

def test_load_application_config_returns_valid_config():
    # Production receives strings from environment variables and converts
    # coordinates to floats before any external request is attempted.
    result = load_application_config(VALID_ENVIRON)

    assert result == ApplicationConfig(
        latitude=48.13,
        longitude=11.57,
        switchbot_token="fake-switchbot-token",
        switchbot_secret="fake-switchbot-secret",
        switchbot_device_id="AABBCCDDEEFF",
        voice_monkey_api_token="fake-voice-monkey-token",
        voice_monkey_open_device_id="fake-open-device",
        voice_monkey_close_device_id="fake-close-device",
    )

@pytest.mark.parametrize(
    "missing_key",
    list(VALID_ENVIRON.keys()),
)
def test_load_application_config_rejects_missing_variable(missing_key):
    # copy() prevents one parameterized case from mutating the shared fixture
    # used by the remaining cases.
    environ = VALID_ENVIRON.copy()
    del environ[missing_key]

    with pytest.raises(ConfigurationError) as captured:
        load_application_config(environ)

    assert captured.value.code == "MISSING_CONFIGURATION"
    assert captured.value.retryable is False
    assert missing_key in captured.value.message

@pytest.mark.parametrize(
    "key",
    [
        "WEATHER_LATITUDE",
        "WEATHER_LONGITUDE",
    ],
)
def test_load_application_config_rejects_non_numeric_coordinate(key):
    environ = VALID_ENVIRON.copy()
    environ[key] = "not-a-number"

    with pytest.raises(ConfigurationError) as captured:
        load_application_config(environ)

    assert captured.value.code == "INVALID_CONFIGURATION"
    assert captured.value.retryable is False
    assert captured.value.message

@patch(
    "smart_home_qa_harness.application.run_environment_control"
)
@patch(
    "smart_home_qa_harness.application.get_switchbot_indoor_environment"
)
def test_run_application_connects_switchbot_to_orchestrator(
    mock_get_switchbot,
    mock_run_environment_control,
):
    # Arrange: all values are fake and both external-facing functions are
    # patched, so this test cannot contact SwitchBot, weather, or Alexa.
    config = load_application_config(VALID_ENVIRON)
    current_datetime = datetime(
        2026,
        8,
        30,
        20,
        0,
        tzinfo=timezone.utc,
    )
    sent_notification_keys = set()

    expected_result = OrchestrationResult(
        action=WindowAction.OPEN_WINDOWS,
        webhook_sent=True,
    )
    mock_run_environment_control.return_value = expected_result

    # Act: execute only the application wiring.
    result = run_application(
        config=config,
        current_datetime=current_datetime,
        nonce="fake-nonce",
        sent_notification_keys=sent_notification_keys,
    )

    # Assert: the application returns the orchestrator's structured result.
    assert result == expected_result

    mock_run_environment_control.assert_called_once()

    # Inspect how application.py connected configuration, time, and state to
    # the mocked orchestrator.
    call_arguments = mock_run_environment_control.call_args.kwargs

    assert call_arguments["latitude"] == 48.13
    assert call_arguments["longitude"] == 11.57
    assert call_arguments["current_date"] == current_datetime.date()
    assert call_arguments["current_time"].hour == 20
    assert call_arguments["sent_notification_keys"] is sent_notification_keys
    assert call_arguments["api_token"] == "fake-voice-monkey-token"
    assert call_arguments["open_device_id"] == "fake-open-device"
    assert call_arguments["close_device_id"] == "fake-close-device"

    # run_environment_control is mocked, so invoke the supplied provider here
    # to verify the second half of the wiring into the SwitchBot client.
    provider = call_arguments["inside_environment_provider"]

    mock_get_switchbot.return_value = IndoorEnvironmentData(
        temperature=25.0,
        relative_humidity=47.0,
        retrieved_at="2026-08-30T20:00:00+00:00",
        source="switchbot:AABBCCDDEEFF",
    )

    provider()

    mock_get_switchbot.assert_called_once_with(
        token="fake-switchbot-token",
        secret="fake-switchbot-secret",
        device_id="AABBCCDDEEFF",
        timestamp_ms=int(current_datetime.timestamp() * 1000),
        nonce="fake-nonce",
        retrieved_at=current_datetime.isoformat(),
    )
