import os
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from smart_home_qa_harness.decision_engine import WindowAction
from smart_home_qa_harness.lambda_handler import (
    build_notification_reserver,
    lambda_handler,
)
from smart_home_qa_harness.orchestrator import OrchestrationResult
from smart_home_qa_harness.application import (
    ApplicationConfig,
    ConfigurationError,
)


VALID_ENVIRON = {
    "WEATHER_LATITUDE": "48.13",
    "WEATHER_LONGITUDE": "11.57",
    "SWITCHBOT_TOKEN": "fake-switchbot-token",
    "SWITCHBOT_SECRET": "fake-switchbot-secret",
    "SWITCHBOT_DEVICE_ID": "AABBCCDDEEFF",
    "VOICE_MONKEY_API_TOKEN": "fake-voice-monkey-token",
    "VOICE_MONKEY_OPEN_DEVICE_ID": "fake-open-device",
    "VOICE_MONKEY_CLOSE_DEVICE_ID": "fake-close-device",
    "NOTIFICATION_TABLE_NAME": "fake-notification-table",
}


def test_lambda_handler_returns_successful_open_windows_result():
    fixed_datetime = datetime(
        2026,
        9,
        6,
        20,
        0,
        tzinfo=ZoneInfo("Europe/Berlin"),
    )

    with patch.dict(
        os.environ,
        VALID_ENVIRON,
        clear=True,
    ), patch(
        "smart_home_qa_harness.lambda_handler.datetime"
    ) as mock_datetime, patch(
        "smart_home_qa_harness.lambda_handler.uuid.uuid4"
    ) as mock_uuid, patch(
        "smart_home_qa_harness.lambda_handler."
        "build_notification_reserver"
    ) as mock_build_notification_reserver, patch(
        "smart_home_qa_harness.lambda_handler.run_application"
    ) as mock_run_application:
        mock_datetime.now.return_value = fixed_datetime
        mock_uuid.return_value = "fake-uuid"

        mock_run_application.return_value = OrchestrationResult(
            action=WindowAction.OPEN_WINDOWS,
            webhook_sent=True,
        )

        result = lambda_handler(
            event={},
            context=None,
        )

    assert result == {
        "status": "success",
        "action": "OPEN_WINDOWS",
        "webhook_sent": True,
        "notification_suppressed": False,
        "error_code": None,
    }

    mock_run_application.assert_called_once()

def test_lambda_handler_returns_success_without_sending_webhook():
    with patch.dict(
        os.environ,
        VALID_ENVIRON,
        clear=True,
    ), patch(
        "smart_home_qa_harness.lambda_handler."
        "build_notification_reserver"
    ) as mock_build_notification_reserver, patch(
        "smart_home_qa_harness.lambda_handler.run_application"
    ) as mock_run_application:
        mock_run_application.return_value = OrchestrationResult(
            action=WindowAction.NO_ACTION,
            webhook_sent=False,
        )

        result = lambda_handler(
            event={},
            context=None,
        )

    assert result == {
        "status": "success",
        "action": "NO_ACTION",
        "webhook_sent": False,
        "notification_suppressed": False,
        "error_code": None,
    }

def test_lambda_handler_returns_suppressed_notification():
    with patch.dict(
        os.environ,
        VALID_ENVIRON,
        clear=True,
    ), patch(
        "smart_home_qa_harness.lambda_handler."
        "build_notification_reserver"
    ) as mock_build_notification_reserver, patch(
        "smart_home_qa_harness.lambda_handler.run_application"
    ) as mock_run_application:
        mock_run_application.return_value = OrchestrationResult(
            action=WindowAction.OPEN_WINDOWS,
            webhook_sent=False,
            notification_suppressed=True,
        )

        result = lambda_handler(
            event={},
            context=None,
        )

    assert result["status"] == "success"
    assert result["action"] == "OPEN_WINDOWS"
    assert result["webhook_sent"] is False
    assert result["notification_suppressed"] is True
    assert result["error_code"] is None

def test_lambda_handler_returns_orchestration_error():
    with patch.dict(
        os.environ,
        VALID_ENVIRON,
        clear=True,
    ), patch(
        "smart_home_qa_harness.lambda_handler."
        "build_notification_reserver"
    ) as mock_build_notification_reserver, patch(
        "smart_home_qa_harness.lambda_handler.run_application"
    ) as mock_run_application:
        mock_run_application.return_value = OrchestrationResult(
            action=WindowAction.NO_ACTION,
            webhook_sent=False,
            error_code="WEATHER_TIMEOUT",
        )

        result = lambda_handler(
            event={},
            context=None,
        )

    assert result == {
        "status": "error",
        "action": "NO_ACTION",
        "webhook_sent": False,
        "notification_suppressed": False,
        "error_code": "WEATHER_TIMEOUT",
    }

def test_lambda_handler_rejects_missing_configuration():
    with patch.dict(
        os.environ,
        {},
        clear=True,
    ), patch(
        "smart_home_qa_harness.lambda_handler."
        "build_notification_reserver"
    ) as mock_build_notification_reserver, patch(
        "smart_home_qa_harness.lambda_handler.run_application"
    ) as mock_run_application:
        with pytest.raises(ConfigurationError) as captured:
            lambda_handler(
                event={},
                context=None,
            )

    assert captured.value.code == "MISSING_CONFIGURATION"
    assert "WEATHER_LATITUDE" in captured.value.message
    mock_run_application.assert_not_called()

def test_lambda_handler_passes_expected_arguments_to_application():
    fixed_datetime = datetime(
        2026,
        9,
        6,
        20,
        0,
        tzinfo=ZoneInfo("Europe/Berlin"),
    )

    with patch.dict(
        os.environ,
        VALID_ENVIRON,
        clear=True,
    ), patch(
        "smart_home_qa_harness.lambda_handler.datetime"
    ) as mock_datetime, patch(
        "smart_home_qa_harness.lambda_handler.uuid.uuid4"
    ) as mock_uuid, patch(
        "smart_home_qa_harness.lambda_handler."
        "build_notification_reserver"
    ) as mock_build_notification_reserver, patch(
        "smart_home_qa_harness.lambda_handler.run_application"
    ) as mock_run_application:
        mock_datetime.now.return_value = fixed_datetime
        mock_uuid.return_value = "fake-uuid"

        mock_run_application.return_value = OrchestrationResult(
            action=WindowAction.NO_ACTION,
            webhook_sent=False,
        )

        lambda_handler(
            event={"source": "aws.scheduler"},
            context=None,
        )

        mock_run_application.assert_called_once()

        arguments = mock_run_application.call_args.kwargs

    assert arguments["config"] == ApplicationConfig(
        latitude=48.13,
        longitude=11.57,
        switchbot_token="fake-switchbot-token",
        switchbot_secret="fake-switchbot-secret",
        switchbot_device_id="AABBCCDDEEFF",
        voice_monkey_api_token="fake-voice-monkey-token",
        voice_monkey_open_device_id="fake-open-device",
        voice_monkey_close_device_id="fake-close-device",
    )
    assert arguments["current_datetime"] == fixed_datetime
    assert arguments["nonce"] == "fake-uuid"
    assert (
        arguments["reserve_notification"]
        is mock_build_notification_reserver.return_value
    )

    mock_build_notification_reserver.assert_called_once_with(
        table_name="fake-notification-table",
        current_datetime=fixed_datetime,
    )

    mock_datetime.now.assert_called_once_with(
        ZoneInfo("Europe/Berlin"),
    )
    mock_uuid.assert_called_once_with()

@patch(
    "smart_home_qa_harness.lambda_handler."
    "DynamoDBNotificationStore"
)
@patch(
    "smart_home_qa_harness.lambda_handler.boto3.resource"
)
def test_build_notification_reserver_reserves_key_with_expiration(
    mock_boto3_resource,
    mock_store_class,
):
    # Arrange
    current_datetime = datetime(
        2026,
        9,
        6,
        20,
        0,
        tzinfo=ZoneInfo("Europe/Berlin"),
    )

    mock_table = mock_boto3_resource.return_value.Table.return_value
    mock_store = mock_store_class.return_value
    mock_store.reserve.return_value = True

    reserver = build_notification_reserver(
        table_name="fake-notification-table",
        current_datetime=current_datetime,
    )

    # Act
    result = reserver(
        "2026-09-06:evening",
    )

    # Assert
    assert result is True

    mock_boto3_resource.assert_called_once_with(
        "dynamodb"
    )

    mock_boto3_resource.return_value.Table.assert_called_once_with(
        "fake-notification-table"
    )

    mock_store_class.assert_called_once_with(
        table=mock_table,
    )

    expected_expiration = int(
        (
            current_datetime
            + timedelta(days=30)
        ).timestamp()
    )

    mock_store.reserve.assert_called_once_with(
        notification_key="2026-09-06:evening",
        expires_at=expected_expiration,
    )

def test_lambda_handler_rejects_missing_notification_table():
    environ = VALID_ENVIRON.copy()
    del environ["NOTIFICATION_TABLE_NAME"]

    with patch.dict(
        os.environ,
        environ,
        clear=True,
    ), patch(
        "smart_home_qa_harness.lambda_handler."
        "build_notification_reserver"
    ) as mock_build_notification_reserver, patch(
        "smart_home_qa_harness.lambda_handler.run_application"
    ) as mock_run_application:
        with pytest.raises(ConfigurationError) as captured:
            lambda_handler(
                event={},
                context=None,
            )

    assert captured.value.code == "MISSING_CONFIGURATION"
    assert captured.value.retryable is False
    assert "NOTIFICATION_TABLE_NAME" in captured.value.message
    mock_build_notification_reserver.assert_not_called()
    mock_run_application.assert_not_called()
