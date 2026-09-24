"""SwitchBot Relay Switch 2PM status and command client."""

from dataclasses import dataclass
from enum import Enum

import requests

from smart_home_qa_harness.inside_environment_client import (
    SWITCHBOT_BASE_URL,
    SWITCHBOT_TIMEOUT_SECONDS,
    build_switchbot_headers,
)


class RelayState(Enum):
    OFF = "OFF"
    ON = "ON"


@dataclass(frozen=True)
class RelayChannelStatus:
    device_id: str
    channel: int
    state: RelayState
    online: bool


class SwitchBotRelayError(Exception):
    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def get_relay_channel_status(
    token: str,
    secret: str,
    device_id: str,
    channel: int,
    timestamp_ms: int,
    nonce: str,
) -> RelayChannelStatus:
    _validate_device_and_channel(device_id, channel)
    headers = build_switchbot_headers(token, secret, timestamp_ms, nonce)
    payload = _request_json(
        method="GET",
        url=f"{SWITCHBOT_BASE_URL}/devices/{device_id}/status",
        headers=headers,
    )
    return parse_relay_channel_status(payload, device_id, channel)


def set_relay_channel_state(
    token: str,
    secret: str,
    device_id: str,
    channel: int,
    state: RelayState,
    timestamp_ms: int,
    nonce: str,
) -> None:
    _validate_device_and_channel(device_id, channel)
    if not isinstance(state, RelayState):
        raise SwitchBotRelayError(
            "INVALID_RELAY_STATE",
            "Relay state must be ON or OFF.",
            False,
        )

    headers = build_switchbot_headers(token, secret, timestamp_ms, nonce)
    payload = _request_json(
        method="POST",
        url=f"{SWITCHBOT_BASE_URL}/devices/{device_id}/commands",
        headers=headers,
        json={
            "command": "turnOn" if state is RelayState.ON else "turnOff",
            "parameter": str(channel),
            "commandType": "command",
        },
    )
    _validate_provider_success(payload)


def parse_relay_channel_status(
    payload: dict,
    expected_device_id: str,
    channel: int,
) -> RelayChannelStatus:
    _validate_device_and_channel(expected_device_id, channel)
    _validate_provider_success(payload)
    try:
        body = payload["body"]
        device_id = body["deviceId"]
        device_type = body["deviceType"]
        online = body["online"]
        raw_state = body[f"switch{channel}Status"]
    except (KeyError, TypeError) as error:
        raise SwitchBotRelayError(
            "SWITCHBOT_RELAY_INVALID_PAYLOAD",
            "SwitchBot relay status has an invalid structure.",
            False,
        ) from error

    if device_id != expected_device_id or device_type != "Relay Switch 2PM":
        raise SwitchBotRelayError(
            "SWITCHBOT_RELAY_DEVICE_MISMATCH",
            "SwitchBot returned a different relay device.",
            False,
        )
    if not isinstance(online, bool):
        raise SwitchBotRelayError(
            "SWITCHBOT_RELAY_INVALID_PAYLOAD",
            "SwitchBot relay online status is invalid.",
            False,
        )
    if not online:
        raise SwitchBotRelayError(
            "SWITCHBOT_RELAY_OFFLINE",
            "SwitchBot relay is offline.",
            True,
        )
    if isinstance(raw_state, bool) or raw_state not in {0, 1}:
        raise SwitchBotRelayError(
            "SWITCHBOT_RELAY_INVALID_PAYLOAD",
            "SwitchBot relay channel state is invalid.",
            False,
        )
    return RelayChannelStatus(
        device_id=device_id,
        channel=channel,
        state=RelayState.ON if raw_state == 1 else RelayState.OFF,
        online=online,
    )


def _request_json(method: str, url: str, headers: dict, json=None) -> dict:
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json,
            timeout=SWITCHBOT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout as error:
        raise SwitchBotRelayError(
            "SWITCHBOT_RELAY_TIMEOUT",
            "SwitchBot relay request timed out.",
            True,
        ) from error
    except requests.exceptions.HTTPError as error:
        status_code = error.response.status_code
        raise SwitchBotRelayError(
            "SWITCHBOT_RELAY_HTTP_ERROR",
            f"SwitchBot relay request failed: {status_code}",
            status_code == 429 or status_code >= 500,
        ) from error
    except requests.exceptions.ConnectionError as error:
        raise SwitchBotRelayError(
            "SWITCHBOT_RELAY_CONNECTION_ERROR",
            "Could not connect to the SwitchBot relay API.",
            True,
        ) from error
    except requests.exceptions.JSONDecodeError as error:
        raise SwitchBotRelayError(
            "SWITCHBOT_RELAY_INVALID_JSON",
            "SwitchBot relay API returned invalid JSON.",
            False,
        ) from error


def _validate_provider_success(payload: dict) -> None:
    try:
        status_code = payload["statusCode"]
    except (KeyError, TypeError) as error:
        raise SwitchBotRelayError(
            "SWITCHBOT_RELAY_INVALID_PAYLOAD",
            "SwitchBot relay response has no valid status code.",
            False,
        ) from error
    if isinstance(status_code, bool) or not isinstance(status_code, int):
        raise SwitchBotRelayError(
            "SWITCHBOT_RELAY_INVALID_PAYLOAD",
            "SwitchBot relay response status code is invalid.",
            False,
        )
    if status_code != 100:
        raise SwitchBotRelayError(
            "SWITCHBOT_RELAY_API_ERROR",
            f"SwitchBot relay API returned status code {status_code}.",
            status_code == 190,
        )


def _validate_device_and_channel(device_id: str, channel: int) -> None:
    if not isinstance(device_id, str) or not device_id.strip():
        raise SwitchBotRelayError(
            "INVALID_RELAY_DEVICE_ID",
            "Relay device ID must be a non-empty string.",
            False,
        )
    if isinstance(channel, bool) or channel not in {1, 2}:
        raise SwitchBotRelayError(
            "INVALID_RELAY_CHANNEL",
            "Relay channel must be 1 or 2.",
            False,
        )
