"""Unit tests for static and SwitchBot indoor environment providers.

Error tests use ``captured.value`` to access the actual exception raised by the
code under test. They verify three parts of the public failure contract:
a stable error code, whether retry is safe, and a readable non-empty message.
All HTTP interactions are intercepted by ``responses``; no real API is called.
"""

import pytest
import responses
import requests

from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentError,
    get_static_indoor_environment,
    parse_switchbot_environment,
    build_switchbot_headers,
    get_switchbot_indoor_environment,
)


def test_static_provider_returns_configured_temperature():
    result = get_static_indoor_environment(
        temperature=23.5,
        retrieved_at="2026-08-16T18:00:00+00:00",
    )

    assert result.temperature == 23.5
    assert result.relative_humidity is None
    assert result.retrieved_at == "2026-08-16T18:00:00+00:00"
    assert result.source == "static-demo"

@pytest.mark.parametrize(
    "temperature",
    ["25,5", "twenty five", "25.5C", None, True, False, [], {}],
)
def test_static_provider_rejects_invalid_temperature(temperature):
    # Act
    with pytest.raises(IndoorEnvironmentError) as captured:
        get_static_indoor_environment(
            temperature=temperature,
            retrieved_at="2026-08-16T18:00:00+00:00",
        )
    assert captured.value.code == "INVALID_ENVIRONMENT_INPUT"
    assert captured.value.retryable is False
    assert captured.value.message

@pytest.mark.parametrize(
    "temperature",
    [0, 23, 23.5, -5.5],
)
def test_static_provider_accepts_numeric_temperature(temperature):
    result = get_static_indoor_environment(
        temperature=temperature,
        retrieved_at="2026-08-16T18:00:00+00:00",
    )

    assert result.temperature == temperature

def test_parses_valid_switchbot_environment_payload():
    # Arrange
    payload = {
        "statusCode": 100,
        "body": {
            "deviceId": "fake-meter-device",
            "deviceType": "Meter",
            "hubDeviceId": "fake-hub-device",
            "humidity": 52,
            "temperature": 22.8,
        },
        "message": "success",
    }

    # Act
    result = parse_switchbot_environment(
        payload=payload,
        retrieved_at="2026-08-16T18:30:00+00:00",
    )

    # Assert
    assert result.temperature == 22.8
    assert result.relative_humidity == 52.0
    assert result.retrieved_at == "2026-08-16T18:30:00+00:00"
    assert result.source == "switchbot:fake-meter-device"
    assert isinstance(result.temperature, float)
    assert isinstance(result.relative_humidity, float)

@pytest.mark.parametrize(
    "payload",
    [
        # Missing body
        {"statusCode": 100, "message": "success"},
        # Missing temperature
        {"statusCode": 100, "body": {"humidity": 50, "deviceId": "fake-device"}, "message": "success"},
        # Missing humidity
        {"statusCode": 100, "body": {"temperature": 22.5, "deviceId": "fake-device"}, "message": "success"},
        # Missing deviceId
        {"statusCode": 100, "body": {"temperature": 22.5, "humidity": 50}, "message": "success"},
        # Invalid temperature type
        {"statusCode": 100, "body": {"temperature": "warm", "humidity": 50, "deviceId": "fake-device"}, "message": "success"},
        # Invalid humidity type
        {"statusCode": 100, "body": {"temperature": 22.5, "humidity": True, "deviceId": "fake-device"}, "message": "success"},
        # Invalid humidity value (negative)
        {"statusCode": 100, "body": {"temperature": 22.5, "humidity": -10, "deviceId": "fake-device"}, "message": "success"},
        # Invalid humidity value (greater than 100)
        {"statusCode": 100, "body": {"temperature": 22.5, "humidity": 101, "deviceId": "fake-device"}, "message": "success"},
        #
        {"statusCode": 100, "body": {"temperature": 22.5, "humidity": 50, "deviceId": ""}, "message": "success"},
        #
        {"statusCode": 100, "body": {"temperature": 22.5, "humidity": 50, "deviceId": None}, "message": "success"},
        # Missing statusCode
        {"body": {"temperature": 22.5, "humidity": 50, "deviceId": "fake-device"}, "message": "success"},
        # Invalid statusCode type
        {"statusCode": "success", "body": {"temperature": 22.5, "humidity": 50, "deviceId": "fake-device"}, "message": "success"},
    ],
)
def test_rejects_invalid_switchbot_environment_payload(payload):
    # Act
    with pytest.raises(IndoorEnvironmentError) as captured:
        parse_switchbot_environment(
            payload=payload,
            retrieved_at="2026-08-16T18:30:00+00:00",
    )
    # Assert
    assert captured.value.code == "SWITCHBOT_INVALID_PAYLOAD"
    assert captured.value.retryable is False
    assert captured.value.message

def test_build_switchbot_headers_returns_signed_headers():
    # Fixed inputs make the HMAC signature deterministic and regression-testable.
    headers = build_switchbot_headers(
        token="fake-token",
        secret="fake-secret",
        timestamp_ms=1724000000000,
        nonce="fake-nonce",
    )

    assert headers["Authorization"] == "fake-token"
    assert headers["t"] == "1724000000000"
    assert headers["nonce"] == "fake-nonce"
    assert headers["Content-Type"] == "application/json; charset=utf8"
    # A non-empty check would allow an incorrect signature such as "anything".
    assert headers["sign"] == "1ZVESFUL/BUP7RLDRMXFQBP+JQSMFNDMKSXENPLRJ7K="

@pytest.mark.parametrize(
    "credentials",
    [
        {"token": "", "secret": "fake-secret", "timestamp_ms": 1724000000000, "nonce": "fake-nonce"},
        {"token": "fake-token", "secret": "", "timestamp_ms": 1724000000000, "nonce": "fake-nonce"},
        {"token": "fake-token", "secret": "fake-secret", "timestamp_ms": 1724000000000, "nonce": ""},
        {"token": "fake-token", "secret": "fake-secret", "timestamp_ms": True, "nonce": "fake-nonce"},
    ],
)
def test_build_switchbot_headers_rejects_invalid_headers(credentials):
    # Act
    with pytest.raises(IndoorEnvironmentError) as captured:
       build_switchbot_headers(**credentials)

    # Assert
    assert captured.value.code == "SWITCHBOT_INVALID_CREDENTIALS"
    assert captured.value.retryable is False

@responses.activate
def test_get_switchbot_environment_returns_meter_data():
    # Arrange
    device_id = "fake-meter-device"
    url = (
        "https://api.switch-bot.com/v1.1/"
        f"devices/{device_id}/status"
    )

    responses.add(
        responses.GET,
        url,
        json={
            "statusCode": 100,
            "body": {
                "deviceId": device_id,
                "deviceType": "Meter",
                "hubDeviceId": "fake-hub-device",
                "humidity": 52,
                "temperature": 22.8,
            },
            "message": "success",
        },
        status=200,
    )

    # Act
    result = get_switchbot_indoor_environment(
        token="fake-token",
        secret="fake-secret",
        device_id=device_id,
        timestamp_ms=1724000000000,
        nonce="fake-nonce",
        retrieved_at="2026-08-22T18:30:00+00:00",
    )

    # Assert: result
    assert result.temperature == 22.8
    assert result.relative_humidity == 52.0
    assert result.source == "switchbot:fake-meter-device"

    # Assert the integration contract as well as the returned measurements.
    assert len(responses.calls) == 1
    request = responses.calls[0].request

    assert request.headers["Authorization"] == "fake-token"
    assert request.headers["t"] == "1724000000000"
    assert request.headers["nonce"] == "fake-nonce"
    assert request.headers["sign"] == (
        "1ZVESFUL/BUP7RLDRMXFQBP+JQSMFNDMKSXENPLRJ7K="
    )

@responses.activate
def test_get_switchbot_raises_timeout():
    # Arrange
    device_id = "fake-meter-device"
    url = (
        "https://api.switch-bot.com/v1.1/"
        f"devices/{device_id}/status"
    )

    responses.add(
        responses.GET,
        url,
        body=requests.exceptions.Timeout("Server took too long to respond"),
    )

    # Act
    with pytest.raises(IndoorEnvironmentError) as captured:
        get_switchbot_indoor_environment(
            token="fake-token",
            secret="fake-secret",
            device_id=device_id,
            timestamp_ms=1724000000000,
            nonce="fake-nonce",
            retrieved_at="2026-08-22T18:30:00+00:00",
        )

    # Assert
    assert captured.value.code == "SWITCHBOT_TIMEOUT"
    assert captured.value.retryable is True
    assert captured.value.message

@responses.activate
def test_get_switchbot_returns_http_500():
    # Arrange
    device_id = "fake-meter-device"
    url = (
        "https://api.switch-bot.com/v1.1/"
        f"devices/{device_id}/status"
    )

    responses.add(
        responses.GET,
        url,
        json={"message": "Internal server error"},
        status=500
    )

    # Act
    with pytest.raises(IndoorEnvironmentError) as captured:
        get_switchbot_indoor_environment(
            token="fake-token",
            secret="fake-secret",
            device_id=device_id,
            timestamp_ms=1724000000000,
            nonce="fake-nonce",
            retrieved_at="2026-08-22T18:30:00+00:00",
        )

    # Assert
    assert captured.value.code == "SWITCHBOT_HTTP_ERROR"
    assert captured.value.retryable is True
    assert "500" in captured.value.message

@responses.activate
def test_get_switchbot_returns_http_401():
    # Arrange
    device_id = "fake-meter-device"
    url = (
        "https://api.switch-bot.com/v1.1/"
        f"devices/{device_id}/status"
    )

    responses.add(
        responses.GET,
        url,
        json={"message": "Unauthorized"},
        status=401,
    )

    # Act
    with pytest.raises(IndoorEnvironmentError) as captured:
        get_switchbot_indoor_environment(
            token="fake-token",
            secret="fake-secret",
            device_id=device_id,
            timestamp_ms=1724000000000,
            nonce="fake-nonce",
            retrieved_at="2026-08-22T18:30:00+00:00",
        )

    # Assert
    assert captured.value.code == "SWITCHBOT_HTTP_ERROR"
    assert captured.value.retryable is False
    assert "401" in captured.value.message

@responses.activate
def test_get_switchbot_translates_invalid_json():
    device_id = "fake-meter-device"
    url = (
        "https://api.switch-bot.com/v1.1/"
        f"devices/{device_id}/status"
    )

    responses.add(
        responses.GET,
        url,
        body="{this is broken",
        status=200,
        content_type="application/json",
    )

    with pytest.raises(IndoorEnvironmentError) as captured:
        get_switchbot_indoor_environment(
            token="fake-token",
            secret="fake-secret",
            device_id=device_id,
            timestamp_ms=1724000000000,
            nonce="fake-nonce",
            retrieved_at="2026-08-22T18:30:00+00:00",
        )

    assert captured.value.code == "SWITCHBOT_INVALID_JSON"
    assert captured.value.retryable is False
    assert captured.value.message

def test_parse_switchbot_translates_api_status_190():
    # SwitchBot may report a provider failure inside an HTTP 200 response.
    payload = {
        "statusCode": 190,
        "body": {},
        "message": "System error",
    }

    with pytest.raises(IndoorEnvironmentError) as captured:
        parse_switchbot_environment(
            payload=payload,
            retrieved_at="2026-08-26T18:30:00+00:00",
        )

    assert captured.value.code == "SWITCHBOT_API_ERROR"
    assert captured.value.retryable is True
    assert "190" in captured.value.message
    assert "System error" in captured.value.message

@responses.activate
def test_get_switchbot_rejects_different_device_id():
    # A valid measurement from the wrong room must not drive an automation.
    requested_device_id = "living-room-meter"
    url = (
        "https://api.switch-bot.com/v1.1/"
        f"devices/{requested_device_id}/status"
    )

    responses.add(
        responses.GET,
        url,
        json={
            "statusCode": 100,
            "body": {
                "deviceId": "bedroom-meter",
                "humidity": 52,
                "temperature": 22.8,
            },
            "message": "success",
        },
        status=200,
    )

    with pytest.raises(IndoorEnvironmentError) as captured:
        get_switchbot_indoor_environment(
            token="fake-token",
            secret="fake-secret",
            device_id=requested_device_id,
            timestamp_ms=1724000000000,
            nonce="fake-nonce",
            retrieved_at="2026-08-29T18:30:00+00:00",
        )

    assert captured.value.code == "SWITCHBOT_DEVICE_MISMATCH"
    assert captured.value.retryable is False
    assert captured.value.message

@responses.activate
def test_get_switchbot_translates_http_429_as_retryable():
    # Rate limiting is temporary, unlike most other HTTP 4xx responses.
    device_id = "fake-meter-device"
    url = (
        "https://api.switch-bot.com/v1.1/"
        f"devices/{device_id}/status"
    )

    responses.add(
        responses.GET,
        url,
        json={"message": "Too Many Requests"},
        status=429,
    )

    with pytest.raises(IndoorEnvironmentError) as captured:
        get_switchbot_indoor_environment(
            token="fake-token",
            secret="fake-secret",
            device_id=device_id,
            timestamp_ms=1724000000000,
            nonce="fake-nonce",
            retrieved_at="2026-08-29T18:30:00+00:00",
        )

    assert captured.value.code == "SWITCHBOT_HTTP_ERROR"
    assert captured.value.retryable is True
    assert "429" in captured.value.message

@pytest.mark.parametrize(
    "device_id",
    ["", "   ", None, True],
)
@responses.activate
def test_get_switchbot_rejects_invalid_requested_device_id(device_id):
    with pytest.raises(IndoorEnvironmentError) as captured:
        get_switchbot_indoor_environment(
            token="fake-token",
            secret="fake-secret",
            device_id=device_id,
            timestamp_ms=1724000000000,
            nonce="fake-nonce",
            retrieved_at="2026-08-29T18:30:00+00:00",
        )

    assert captured.value.code == "SWITCHBOT_INVALID_DEVICE_ID"
    assert captured.value.retryable is False
    # Input validation must happen before any external side effect.
    assert len(responses.calls) == 0

@responses.activate
def test_get_switchbot_translates_connection_error():
    device_id = "fake-meter-device"
    url = (
        "https://api.switch-bot.com/v1.1/"
        f"devices/{device_id}/status"
    )

    responses.add(
        responses.GET,
        url,
        body=requests.exceptions.ConnectionError(
            "Could not connect to SwitchBot",
        ),
    )

    with pytest.raises(IndoorEnvironmentError) as captured:
        get_switchbot_indoor_environment(
            token="fake-token",
            secret="fake-secret",
            device_id=device_id,
            timestamp_ms=1724000000000,
            nonce="fake-nonce",
            retrieved_at="2026-08-29T18:30:00+00:00",
        )

    assert captured.value.code == "SWITCHBOT_CONNECTION_ERROR"
    assert captured.value.retryable is True
    assert captured.value.message
