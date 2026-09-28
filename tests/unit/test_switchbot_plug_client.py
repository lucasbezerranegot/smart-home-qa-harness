import json

import pytest
import requests
import responses

from smart_home_qa_harness.inside_environment_client import SWITCHBOT_BASE_URL
from smart_home_qa_harness.switchbot_plug_client import (
    PlugState,
    SwitchBotPlugError,
    get_plug_status,
    parse_plug_status,
    set_plug_state,
)


DEVICE_ID = "plug-bedroom"


def status_payload(**overrides):
    body = {
        "deviceId": DEVICE_ID,
        "deviceType": "Plug Mini (EU)",
        "switchStatus": 1,
        "voltage": 230.1,
        "power": 22.5,
        "electricCurrent": 98.0,
        "usedElectricity": 120,
    }
    body.update(overrides)
    return {"statusCode": 100, "body": body, "message": "success"}


def test_parses_plug_state_and_keeps_power_as_observation_only():
    result = parse_plug_status(status_payload(), DEVICE_ID)

    assert result.device_id == DEVICE_ID
    assert result.state is PlugState.ON
    assert result.voltage == 230.1
    assert result.power == 22.5
    assert result.electric_current == 98.0
    assert result.used_electricity == 120


@pytest.mark.parametrize(
    "payload,error_code",
    [
        ({"statusCode": 100}, "SWITCHBOT_PLUG_INVALID_PAYLOAD"),
        (status_payload(deviceId="another"), "SWITCHBOT_PLUG_DEVICE_MISMATCH"),
        (status_payload(deviceType="Plug Mini (US)"), "SWITCHBOT_PLUG_DEVICE_MISMATCH"),
        (status_payload(switchStatus=True), "SWITCHBOT_PLUG_INVALID_PAYLOAD"),
        (status_payload(power=-1), "SWITCHBOT_PLUG_INVALID_PAYLOAD"),
        (status_payload(voltage=float("nan")), "SWITCHBOT_PLUG_INVALID_PAYLOAD"),
        (status_payload(electricCurrent="98"), "SWITCHBOT_PLUG_INVALID_PAYLOAD"),
        (status_payload(usedElectricity=-1), "SWITCHBOT_PLUG_INVALID_PAYLOAD"),
        ({"statusCode": 190}, "SWITCHBOT_PLUG_API_ERROR"),
    ],
)
def test_rejects_invalid_status_payload(payload, error_code):
    with pytest.raises(SwitchBotPlugError) as captured:
        parse_plug_status(payload, DEVICE_ID)

    assert captured.value.code == error_code


@responses.activate
def test_gets_status_with_signed_switchbot_request():
    responses.add(
        responses.GET,
        f"{SWITCHBOT_BASE_URL}/devices/{DEVICE_ID}/status",
        json=status_payload(),
        status=200,
    )

    result = get_plug_status(
        token="token",
        secret="secret",
        device_id=DEVICE_ID,
        timestamp_ms=1724000000000,
        nonce="nonce",
    )

    assert result.state is PlugState.ON
    assert responses.calls[0].request.headers["Authorization"] == "token"


@responses.activate
@pytest.mark.parametrize(
    "state,command",
    [(PlugState.ON, "turnOn"), (PlugState.OFF, "turnOff")],
)
def test_sends_plug_commands(state, command):
    responses.add(
        responses.POST,
        f"{SWITCHBOT_BASE_URL}/devices/{DEVICE_ID}/commands",
        json={"statusCode": 100, "body": {}, "message": "success"},
        status=200,
    )

    set_plug_state(
        token="token",
        secret="secret",
        device_id=DEVICE_ID,
        state=state,
        timestamp_ms=1724000000000,
        nonce="nonce",
    )

    assert json.loads(responses.calls[0].request.body) == {
        "command": command,
        "parameter": "default",
        "commandType": "command",
    }


@responses.activate
@pytest.mark.parametrize(
    "body,expected_code,retryable",
    [
        (requests.exceptions.Timeout(), "SWITCHBOT_PLUG_TIMEOUT", True),
        (requests.exceptions.ConnectionError(), "SWITCHBOT_PLUG_CONNECTION_ERROR", True),
    ],
)
def test_translates_transport_failures(body, expected_code, retryable):
    responses.add(
        responses.GET,
        f"{SWITCHBOT_BASE_URL}/devices/{DEVICE_ID}/status",
        body=body,
    )

    with pytest.raises(SwitchBotPlugError) as captured:
        get_plug_status("token", "secret", DEVICE_ID, 1724000000000, "nonce")

    assert captured.value.code == expected_code
    assert captured.value.retryable is retryable


@responses.activate
@pytest.mark.parametrize("http_status,retryable", [(400, False), (429, True), (500, True)])
def test_translates_http_failures(http_status, retryable):
    responses.add(
        responses.GET,
        f"{SWITCHBOT_BASE_URL}/devices/{DEVICE_ID}/status",
        status=http_status,
    )

    with pytest.raises(SwitchBotPlugError) as captured:
        get_plug_status("token", "secret", DEVICE_ID, 1724000000000, "nonce")

    assert captured.value.code == "SWITCHBOT_PLUG_HTTP_ERROR"
    assert captured.value.retryable is retryable


@responses.activate
def test_rejects_invalid_device_before_http_call():
    with pytest.raises(SwitchBotPlugError) as captured:
        get_plug_status("token", "secret", "", 1724000000000, "nonce")

    assert captured.value.code == "INVALID_PLUG_DEVICE_ID"
    assert not responses.calls


@responses.activate
def test_translates_invalid_json():
    responses.add(
        responses.GET,
        f"{SWITCHBOT_BASE_URL}/devices/{DEVICE_ID}/status",
        body="{broken",
        status=200,
        content_type="application/json",
    )

    with pytest.raises(SwitchBotPlugError) as captured:
        get_plug_status("token", "secret", DEVICE_ID, 1724000000000, "nonce")

    assert captured.value.code == "SWITCHBOT_PLUG_INVALID_JSON"


def test_rejects_non_enum_command_state():
    with pytest.raises(SwitchBotPlugError) as captured:
        set_plug_state("token", "secret", DEVICE_ID, "ON", 1, "nonce")

    assert captured.value.code == "INVALID_PLUG_STATE"
