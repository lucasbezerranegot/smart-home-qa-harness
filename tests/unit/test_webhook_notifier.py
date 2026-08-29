import json
import pytest
import responses
import requests

from smart_home_qa_harness.decision_engine import WindowAction
from smart_home_qa_harness.webhook_notifier import WebhookError, send_window_action, VOICE_MONKEY_TRIGGER_URL

@responses.activate
@pytest.mark.parametrize(
    "action, expected_device",
    [
        (
            WindowAction.OPEN_WINDOWS,
            "fake-open-device",
        ),
        (
            WindowAction.CLOSE_WINDOWS,
            "fake-close-device",
        ),
    ],
)
def test_sends_window_action_to_webhook(action: WindowAction, expected_device: str):
    # Arrange
    api_token = "fake-test-token"
    open_device_id = "fake-open-device"
    close_device_id = "fake-close-device"

    responses.add(
        responses.POST,
        VOICE_MONKEY_TRIGGER_URL,
        status=200,
    )

    # Act
    result = send_window_action(
        api_token=api_token,
        action=action,
        open_device_id=open_device_id,
        close_device_id=close_device_id,
    )

    # Assert: successful commands return no value
    assert result is None

    # Assert: exactly one HTTP request was sent
    assert len(responses.calls) == 1

    request = responses.calls[0].request

    # Assert: decode the request body and inspect it
    sent_payload = json.loads(request.body)
    assert sent_payload == {
        "token": "fake-test-token",
        "device": expected_device,
    }

@responses.activate
def test_no_action_does_not_send_window_action_to_webhook():
    # Arrange
    api_token = "fake-test-token"
    open_device_id = "fake-open-device"
    close_device_id = "fake-close-device"

    # Act
    result = send_window_action(
        api_token=api_token,
        action=WindowAction.NO_ACTION,
        open_device_id=open_device_id,
        close_device_id=close_device_id,
    )

    # Assert: successful commands return no value
    assert result is None

    # Assert: no HTTP request was sent
    assert len(responses.calls) == 0

@responses.activate
def test_translates_webhook_timeout_to_retryable_error():
    # Arrange
    api_token = "fake-test-token"
    open_device_id = "fake-open-device"
    close_device_id = "fake-close-device"

    responses.add(
        responses.POST,
        VOICE_MONKEY_TRIGGER_URL,
        body=requests.exceptions.Timeout(
            "Webhook took too long to respond"
        ),
    )

    # Act
    with pytest.raises(WebhookError) as captured:
        send_window_action(
            api_token=api_token,
            action=WindowAction.OPEN_WINDOWS,
            open_device_id=open_device_id,
            close_device_id=close_device_id,
        )

    # Assert
    # Assert: exactly one HTTP request was sent
    assert len(responses.calls) == 1
    request = responses.calls[0].request

    # Assert: timeout errors are translated to retryable WebhookError
    error = captured.value
    assert error.code == "WEBHOOK_TIMEOUT"
    assert error.retryable is True
    assert error.message

@responses.activate
def test_translates_http_500_to_retryable_error():
    # Arrange
    api_token = "fake-test-token"
    open_device_id = "fake-open-device"
    close_device_id = "fake-close-device"

    responses.add(
        responses.POST,
        VOICE_MONKEY_TRIGGER_URL,
        status=500,
        json={"error": "Internal Server Error"},
    )

    # Act
    with pytest.raises(WebhookError) as captured:
        send_window_action(
            api_token=api_token,
            action=WindowAction.OPEN_WINDOWS,
            open_device_id=open_device_id,
            close_device_id=close_device_id,
        )

    # Assert
    assert captured.value.code == "WEBHOOK_HTTP_ERROR"
    assert captured.value.retryable is True
    assert captured.value.message

@responses.activate
def test_translates_http_429_to_retryable_error():
    # Arrange
    api_token = "fake-test-token"
    open_device_id = "fake-open-device"
    close_device_id = "fake-close-device"

    responses.add(
        responses.POST,
        VOICE_MONKEY_TRIGGER_URL,
        status=429,
        json={"error": "Too Many Requests"},
    )

    # Act
    with pytest.raises(WebhookError) as captured:
        send_window_action(
            api_token=api_token,
            action=WindowAction.OPEN_WINDOWS,
            open_device_id=open_device_id,
            close_device_id=close_device_id,
        )

    # Assert
    assert captured.value.code == "WEBHOOK_HTTP_ERROR"
    assert captured.value.retryable is True
    assert captured.value.message

@responses.activate
def test_translates_http_400_to_non_retryable_error():
    # Arrange
    api_token = "fake-test-token"
    open_device_id = "fake-open-device"
    close_device_id = "fake-close-device"

    responses.add(
        responses.POST,
        VOICE_MONKEY_TRIGGER_URL,
        status=400,
        json={"error": "Bad Request"},
    )

    # Act
    with pytest.raises(WebhookError) as captured:
        send_window_action(
            api_token=api_token,
            action=WindowAction.OPEN_WINDOWS,
            open_device_id=open_device_id,
            close_device_id=close_device_id,
        )

    # Assert
    assert captured.value.code == "WEBHOOK_HTTP_ERROR"
    assert captured.value.retryable is False
    assert captured.value.message

@responses.activate
@pytest.mark.parametrize(
     "api_token, action, open_device_id, close_device_id",
    [
        ("", WindowAction.OPEN_WINDOWS, "open-id", "close-id"),
        ("   ", WindowAction.OPEN_WINDOWS, "open-id", "close-id"),
        ("token", WindowAction.OPEN_WINDOWS, "", "close-id"),
        ("token", WindowAction.CLOSE_WINDOWS, "open-id", ""),
        ("token", "OPEN_WINDOWS", "open-id", "close-id"),
        (None, WindowAction.OPEN_WINDOWS, "open-id", "close-id"),
        (123, WindowAction.OPEN_WINDOWS, "open-id", "close-id"),
        ("token", WindowAction.OPEN_WINDOWS, None, "close-id"),
        ("token", WindowAction.CLOSE_WINDOWS, "open-id", 123),
    ],
)
def test_invalid_inputs_raise_non_retryable_error(
    api_token,
    action,
    open_device_id,
    close_device_id,
):
    # Act
    with pytest.raises(WebhookError) as captured:
        send_window_action(
            api_token=api_token,
            action=action,
            open_device_id=open_device_id,
            close_device_id=close_device_id,
        )

    # Assert
    assert captured.value.code == "INVALID_WEBHOOK_INPUT"
    assert captured.value.retryable is False
    assert captured.value.message
    assert len(responses.calls) == 0
