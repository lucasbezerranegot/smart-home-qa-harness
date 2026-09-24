import json

import pytest
import responses

from smart_home_qa_harness.switchbot_relay_client import (
    RelayState,
    SwitchBotRelayError,
    get_relay_channel_status,
    parse_relay_channel_status,
    set_relay_channel_state,
)


DEVICE_ID = "fake-relay-3"


def status_payload(channel_1=0, channel_2=1, online=True):
    return {
        "statusCode": 100,
        "body": {
            "deviceId": DEVICE_ID,
            "deviceType": "Relay Switch 2PM",
            "online": online,
            "switch1Status": channel_1,
            "switch2Status": channel_2,
        },
        "message": "success",
    }


@pytest.mark.parametrize(
    ("channel", "expected_state"),
    [(1, RelayState.OFF), (2, RelayState.ON)],
)
def test_parses_selected_relay_channel(channel, expected_state):
    result = parse_relay_channel_status(status_payload(), DEVICE_ID, channel)

    assert result.device_id == DEVICE_ID
    assert result.channel == channel
    assert result.state is expected_state
    assert result.online is True


def test_rejects_offline_relay():
    with pytest.raises(SwitchBotRelayError) as captured:
        parse_relay_channel_status(status_payload(online=False), DEVICE_ID, 2)

    assert captured.value.code == "SWITCHBOT_RELAY_OFFLINE"
    assert captured.value.retryable is True


@responses.activate
def test_gets_relay_channel_status_with_signed_request():
    responses.get(
        f"https://api.switch-bot.com/v1.1/devices/{DEVICE_ID}/status",
        json=status_payload(),
        status=200,
    )

    result = get_relay_channel_status(
        token="fake-token",
        secret="fake-secret",
        device_id=DEVICE_ID,
        channel=2,
        timestamp_ms=1724000000000,
        nonce="fake-nonce",
    )

    assert result.state is RelayState.ON
    assert responses.calls[0].request.headers["Authorization"] == "fake-token"


@responses.activate
@pytest.mark.parametrize(
    ("state", "expected_command"),
    [(RelayState.ON, "turnOn"), (RelayState.OFF, "turnOff")],
)
def test_sends_channel_specific_command(state, expected_command):
    responses.post(
        f"https://api.switch-bot.com/v1.1/devices/{DEVICE_ID}/commands",
        json={"statusCode": 100, "body": {}, "message": "success"},
        status=200,
    )

    set_relay_channel_state(
        token="fake-token",
        secret="fake-secret",
        device_id=DEVICE_ID,
        channel=2,
        state=state,
        timestamp_ms=1724000000000,
        nonce="fake-nonce",
    )

    request = responses.calls[0].request
    assert json.loads(request.body) == {
        "command": expected_command,
        "parameter": "2",
        "commandType": "command",
    }


@responses.activate
def test_translates_provider_error_inside_http_success():
    responses.post(
        f"https://api.switch-bot.com/v1.1/devices/{DEVICE_ID}/commands",
        json={"statusCode": 190, "body": {}, "message": "System error"},
        status=200,
    )

    with pytest.raises(SwitchBotRelayError) as captured:
        set_relay_channel_state(
            token="fake-token",
            secret="fake-secret",
            device_id=DEVICE_ID,
            channel=2,
            state=RelayState.OFF,
            timestamp_ms=1724000000000,
            nonce="fake-nonce",
        )

    assert captured.value.code == "SWITCHBOT_RELAY_API_ERROR"
    assert captured.value.retryable is True
