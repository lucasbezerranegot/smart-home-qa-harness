import pytest
from datetime import date, time
from unittest.mock import Mock, patch
from smart_home_qa_harness.decision_engine import WindowAction
from smart_home_qa_harness.orchestrator import (
    OrchestrationResult,
    build_notification_key,
    run_environment_control,
)
from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentData,
    IndoorEnvironmentError,
)
from smart_home_qa_harness.weather_client import (
    WeatherClientError,
    WeatherData,
)
from smart_home_qa_harness.webhook_notifier import WebhookError

@patch("smart_home_qa_harness.orchestrator.send_window_action")
@patch("smart_home_qa_harness.orchestrator.decide_window_action")
@patch("smart_home_qa_harness.orchestrator.get_hourly_forecast")
def test_orchestrates_open_windows_action(
    mock_get_forecast,
    mock_decide_action,
    mock_send_action,
):
    # Arrange
    sent_notification_keys = set()

    mock_get_forecast.return_value = WeatherData(
        outside_temperature=18.0,
        timestamp="2026-08-15T20:00",
    )

    mock_inside_provider = Mock(
        return_value=IndoorEnvironmentData(
            temperature=24.0,
            relative_humidity=47.0,
            retrieved_at="2026-08-29T18:05:47+00:00",
            source="switchbot:fake-meter-device",
        )
    )

    mock_decide_action.return_value = WindowAction.OPEN_WINDOWS

    # Act
    result = run_environment_control(
        latitude=48.13,
        longitude=11.57,
        inside_environment_provider=mock_inside_provider,
        current_time=time(20, 0),
        current_date=date(2026, 8, 29),
        sent_notification_keys=sent_notification_keys,
        api_token="fake-token",
        open_device_id="fake-open-device",
        close_device_id="fake-close-device",
    )

    # Assert result
    assert result == OrchestrationResult(
        action=WindowAction.OPEN_WINDOWS,
        webhook_sent=True,
        error_code=None,
    )

    mock_get_forecast.assert_called_once_with(
        latitude=48.13,
        longitude=11.57,
    )

    mock_decide_action.assert_called_once_with(
        outside_temperature=18.0,
        inside_temperature=24.0,
        current_time=time(20, 0),
    )

    mock_send_action.assert_called_once_with(
        api_token="fake-token",
        action=WindowAction.OPEN_WINDOWS,
        open_device_id="fake-open-device",
        close_device_id="fake-close-device",
    )

    mock_inside_provider.assert_called_once_with()

    assert sent_notification_keys == {
        "2026-08-29:evening",
    }


@patch("smart_home_qa_harness.orchestrator.send_window_action")
@patch("smart_home_qa_harness.orchestrator.decide_window_action")
@patch("smart_home_qa_harness.orchestrator.get_hourly_forecast")
def test_no_action_does_not_send_webhook(
    mock_get_forecast,
    mock_decide_action,
    mock_send_action,
):
    # Arrange
    sent_notification_keys = set()

    mock_get_forecast.return_value = WeatherData(
        outside_temperature=24.0,
        timestamp="2026-08-15T14:00",
    )

    mock_inside_provider = Mock(
        return_value=IndoorEnvironmentData(
            temperature=24.0,
            relative_humidity=47.0,
            retrieved_at="2026-08-29T18:05:47+00:00",
            source="switchbot:fake-meter-device",
        )
    )

    mock_decide_action.return_value = WindowAction.NO_ACTION

    # Act
    result = run_environment_control(
        latitude=48.13,
        longitude=11.57,
        inside_environment_provider=mock_inside_provider,
        current_time=time(14, 0),
        current_date=date(2026, 8, 29),
        sent_notification_keys=sent_notification_keys,
        api_token="fake-token",
        open_device_id="fake-open-device",
        close_device_id="fake-close-device",
    )

    # Assert result
    assert result == OrchestrationResult(
        action=WindowAction.NO_ACTION,
        webhook_sent=False,
        error_code=None,
    )

    # Assert side effect
    mock_send_action.assert_not_called()
    mock_inside_provider.assert_called_once_with()

    assert sent_notification_keys == set()

@patch("smart_home_qa_harness.orchestrator.send_window_action")
@patch("smart_home_qa_harness.orchestrator.decide_window_action")
@patch("smart_home_qa_harness.orchestrator.get_hourly_forecast")
def test_weather_failure_does_not_send_webhook(
    mock_get_forecast,
    mock_decide_action,
    mock_send_action,
):
    # Arrange
    sent_notification_keys = set()

    mock_get_forecast.side_effect = WeatherClientError(
        code="TIMEOUT",
        message="Weather API timed out.",
        retryable=True,
    )
    mock_inside_provider = Mock()

    # Act
    result = run_environment_control(
        latitude=48.13,
        longitude=11.57,
        inside_environment_provider=mock_inside_provider,
        current_time=time(20, 0),
        current_date=date(2026, 8, 29),
        sent_notification_keys=sent_notification_keys,
        api_token="fake-token",
        open_device_id="fake-open-device",
        close_device_id="fake-close-device",
    )

    # Assert the safe result
    assert result == OrchestrationResult(
        action=WindowAction.NO_ACTION,
        webhook_sent=False,
        error_code="TIMEOUT",
    )

    # Assert that processing stopped after the weather failure
    mock_inside_provider.assert_not_called()
    mock_decide_action.assert_not_called()
    mock_send_action.assert_not_called()

    assert sent_notification_keys == set()

@patch("smart_home_qa_harness.orchestrator.send_window_action")
@patch("smart_home_qa_harness.orchestrator.decide_window_action")
@patch("smart_home_qa_harness.orchestrator.get_hourly_forecast")
def test_switchbot_failure_does_not_send_webhook(
    mock_get_forecast,
    mock_decide_action,
    mock_send_action,
):
    # Arrange
    sent_notification_keys = set()

    mock_get_forecast.return_value = WeatherData(
        outside_temperature=24.0,
        timestamp="2026-08-15T14:00",
    )

    mock_inside_provider = Mock(
        side_effect=IndoorEnvironmentError(
            code="SWITCHBOT_TIMEOUT",
            message="SwitchBot API timed out.",
            retryable=True,
        )
    )

    # Act
    result = run_environment_control(
        latitude=48.13,
        longitude=11.57,
        inside_environment_provider=mock_inside_provider,
        current_time=time(20, 0),
        current_date=date(2026, 8, 29),
        sent_notification_keys=sent_notification_keys,
        api_token="fake-token",
        open_device_id="fake-open-device",
        close_device_id="fake-close-device",
    )

    # Assert the safe result
    assert result == OrchestrationResult(
        action=WindowAction.NO_ACTION,
        webhook_sent=False,
        error_code="SWITCHBOT_TIMEOUT",
    )

    # Assert that processing stopped after the switchbot failure
    mock_get_forecast.assert_called_once_with(
        latitude=48.13,
        longitude=11.57,
    )
    mock_inside_provider.assert_called_once_with()
    mock_decide_action.assert_not_called()
    mock_send_action.assert_not_called()

    assert sent_notification_keys == set()

@patch("smart_home_qa_harness.orchestrator.send_window_action")
@patch("smart_home_qa_harness.orchestrator.decide_window_action")
@patch("smart_home_qa_harness.orchestrator.get_hourly_forecast")
def test_webhook_failure_returns_unsent_result(
    mock_get_forecast,
    mock_decide_action,
    mock_send_action,
):
    # Arrange:
    sent_notification_keys = set()

    # Both temperature providers succeed
    mock_get_forecast.return_value = WeatherData(
        outside_temperature=18.0,
        timestamp="2026-08-29T20:00",
    )

    mock_inside_provider = Mock(
        return_value=IndoorEnvironmentData(
            temperature=24.0,
            relative_humidity=47.0,
            retrieved_at="2026-08-29T20:00:00+00:00",
            source="switchbot:fake-meter-device",
        )
    )

    mock_decide_action.return_value = WindowAction.OPEN_WINDOWS

    # The notification attempt fails.
    mock_send_action.side_effect = WebhookError(
        code="WEBHOOK_TIMEOUT",
        message="Webhook took too long to respond.",
        retryable=True,
    )

    # Act
    result = run_environment_control(
        latitude=48.13,
        longitude=11.57,
        inside_environment_provider=mock_inside_provider,
        current_time=time(20, 0),
        current_date=date(2026, 8, 29),
        sent_notification_keys=sent_notification_keys,
        api_token="fake-token",
        open_device_id="fake-open-device",
        close_device_id="fake-close-device",
    )

    # Assert
    assert result == OrchestrationResult(
        action=WindowAction.OPEN_WINDOWS,
        webhook_sent=False,
        error_code="WEBHOOK_TIMEOUT",
    )

    mock_send_action.assert_called_once_with(
        api_token="fake-token",
        action=WindowAction.OPEN_WINDOWS,
        open_device_id="fake-open-device",
        close_device_id="fake-close-device",
    )

    assert sent_notification_keys == set()

@pytest.mark.parametrize(
    "action, expected_key",
    [
        (
            WindowAction.OPEN_WINDOWS,
            "2026-08-29:evening",
        ),
        (
            WindowAction.CLOSE_WINDOWS,
            "2026-08-29:morning",
        ),
        (
            WindowAction.NO_ACTION,
            None,
        ),
    ],
)
def test_build_notification_key(action, expected_key):
    result = build_notification_key(
        current_date=date(2026, 8, 29),
        action=action,
    )

    assert result == expected_key

@patch("smart_home_qa_harness.orchestrator.send_window_action")
@patch("smart_home_qa_harness.orchestrator.decide_window_action")
@patch("smart_home_qa_harness.orchestrator.get_hourly_forecast")
def test_duplicate_period_does_not_send_webhook(
    mock_get_forecast,
    mock_decide_action,
    mock_send_action,
):
    mock_get_forecast.return_value = WeatherData(
        outside_temperature=18.0,
        timestamp="2026-08-29T20:00",
    )

    mock_inside_provider = Mock(
        return_value=IndoorEnvironmentData(
            temperature=24.0,
            relative_humidity=47.0,
            retrieved_at="2026-08-29T20:00:00+00:00",
            source="switchbot:fake-meter-device",
        )
    )

    mock_decide_action.return_value = WindowAction.OPEN_WINDOWS

    sent_notification_keys = {
        "2026-08-29:evening",
    }

    result = run_environment_control(
        latitude=48.13,
        longitude=11.57,
        inside_environment_provider=mock_inside_provider,
        current_date=date(2026, 8, 29),
        current_time=time(20, 0),
        sent_notification_keys=sent_notification_keys,
        api_token="fake-token",
        open_device_id="fake-open-device",
        close_device_id="fake-close-device",
    )

    assert result == OrchestrationResult(
        action=WindowAction.OPEN_WINDOWS,
        webhook_sent=False,
        error_code=None,
        notification_suppressed=True,
    )

    mock_send_action.assert_not_called()

@patch("smart_home_qa_harness.orchestrator.send_window_action")
@patch("smart_home_qa_harness.orchestrator.decide_window_action")
@patch("smart_home_qa_harness.orchestrator.get_hourly_forecast")
def test_same_period_sends_webhook_only_once(
    mock_get_forecast,
    mock_decide_action,
    mock_send_action,
):
    # Arrange
    mock_get_forecast.return_value = WeatherData(
        outside_temperature=18.0,
        timestamp="2026-08-30T20:00",
    )

    mock_inside_provider = Mock(
        return_value=IndoorEnvironmentData(
            temperature=24.0,
            relative_humidity=47.0,
            retrieved_at="2026-08-30T20:00:00+00:00",
            source="switchbot:fake-meter-device",
        )
    )

    mock_decide_action.return_value = WindowAction.OPEN_WINDOWS
    sent_notification_keys = set()

    arguments = {
        "latitude": 48.13,
        "longitude": 11.57,
        "inside_environment_provider": mock_inside_provider,
        "current_date": date(2026, 8, 30),
        "current_time": time(20, 0),
        "sent_notification_keys": sent_notification_keys,
        "api_token": "fake-token",
        "open_device_id": "fake-open-device",
        "close_device_id": "fake-close-device",
    }

    # Act
    first_result = run_environment_control(**arguments)
    second_result = run_environment_control(**arguments)

    # Assert
    assert first_result.webhook_sent is True
    assert first_result.notification_suppressed is False

    assert second_result.webhook_sent is False
    assert second_result.notification_suppressed is True

    mock_send_action.assert_called_once()
    assert sent_notification_keys == {
        "2026-08-30:evening",
    }
