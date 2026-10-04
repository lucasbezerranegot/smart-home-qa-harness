"""SwitchBot Plug Mini (EU) status and command adapter."""

from dataclasses import dataclass
from enum import Enum
import math

import requests

from smart_home_qa_harness.inside_environment_client import (
    SWITCHBOT_BASE_URL,
    SWITCHBOT_TIMEOUT_SECONDS,
    build_switchbot_headers,
)


class PlugState(Enum):
    OFF = "OFF"
    ON = "ON"


@dataclass(frozen=True)
class PlugMiniStatus:
    device_id: str
    state: PlugState
    voltage: float
    power: float
    electric_current: float
    used_electricity: int


class SwitchBotPlugError(Exception):
    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def get_plug_status(
    token: str,
    secret: str,
    device_id: str,
    timestamp_ms: int,
    nonce: str,
) -> PlugMiniStatus:
    _validate_device_id(device_id)
    headers = build_switchbot_headers(token, secret, timestamp_ms, nonce)
    payload = _request_json(
        "GET",
        f"{SWITCHBOT_BASE_URL}/devices/{device_id}/status",
        headers,
    )
    return parse_plug_status(payload, expected_device_id=device_id)


def set_plug_state(
    token: str,
    secret: str,
    device_id: str,
    state: PlugState,
    timestamp_ms: int,
    nonce: str,
) -> None:
    _validate_device_id(device_id)
    if not isinstance(state, PlugState):
        raise SwitchBotPlugError(
            "INVALID_PLUG_STATE",
            "Plug state must be ON or OFF.",
            False,
        )

    headers = build_switchbot_headers(token, secret, timestamp_ms, nonce)
    payload = _request_json(
        "POST",
        f"{SWITCHBOT_BASE_URL}/devices/{device_id}/commands",
        headers,
        json={
            "command": "turnOn" if state is PlugState.ON else "turnOff",
            "parameter": "default",
            "commandType": "command",
        },
    )
    _validate_provider_success(payload)


def parse_plug_status(
    payload: dict,
    expected_device_id: str,
) -> PlugMiniStatus:
    _validate_device_id(expected_device_id)
    _validate_provider_success(payload)
    try:
        body = payload["body"]
        device_id = body["deviceId"]
        device_type = body["deviceType"]
        switch_status = body["switchStatus"]
        voltage = body["voltage"]
        power = body["power"]
        electric_current = body["electricCurrent"]
        used_electricity = body["usedElectricity"]
    except (KeyError, TypeError) as error:
        raise SwitchBotPlugError(
            "SWITCHBOT_PLUG_INVALID_PAYLOAD",
            "SwitchBot plug status has an invalid structure.",
            False,
        ) from error

    if device_id != expected_device_id or device_type != "Plug Mini (EU)":
        raise SwitchBotPlugError(
            "SWITCHBOT_PLUG_DEVICE_MISMATCH",
            "SwitchBot returned a different plug device.",
            False,
        )
    if isinstance(switch_status, bool) or switch_status not in {0, 1}:
        raise SwitchBotPlugError(
            "SWITCHBOT_PLUG_INVALID_PAYLOAD",
            "SwitchBot returned an invalid plug state.",
            False,
        )
    for label, value in (
        ("voltage", voltage),
        ("power", power),
        ("electric current", electric_current),
    ):
        if not _is_non_negative_number(value):
            raise SwitchBotPlugError(
                "SWITCHBOT_PLUG_INVALID_PAYLOAD",
                f"SwitchBot returned invalid {label}.",
                False,
            )
    if (
        isinstance(used_electricity, bool)
        or not isinstance(used_electricity, int)
        or used_electricity < 0
    ):
        raise SwitchBotPlugError(
            "SWITCHBOT_PLUG_INVALID_PAYLOAD",
            "SwitchBot returned invalid used electricity.",
            False,
        )

    return PlugMiniStatus(
        device_id=device_id,
        state=PlugState.ON if switch_status == 1 else PlugState.OFF,
        voltage=float(voltage),
        power=float(power),
        electric_current=float(electric_current),
        used_electricity=used_electricity,
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
        raise SwitchBotPlugError(
            "SWITCHBOT_PLUG_TIMEOUT",
            "SwitchBot plug request timed out.",
            True,
        ) from error
    except requests.exceptions.HTTPError as error:
        status_code = error.response.status_code
        raise SwitchBotPlugError(
            "SWITCHBOT_PLUG_HTTP_ERROR",
            f"SwitchBot plug request failed: {status_code}",
            status_code == 429 or status_code >= 500,
        ) from error
    except requests.exceptions.ConnectionError as error:
        raise SwitchBotPlugError(
            "SWITCHBOT_PLUG_CONNECTION_ERROR",
            "Could not connect to the SwitchBot plug API.",
            True,
        ) from error
    except requests.exceptions.JSONDecodeError as error:
        raise SwitchBotPlugError(
            "SWITCHBOT_PLUG_INVALID_JSON",
            "SwitchBot plug API returned invalid JSON.",
            False,
        ) from error


def _validate_provider_success(payload: dict) -> None:
    try:
        status_code = payload["statusCode"]
    except (KeyError, TypeError) as error:
        raise SwitchBotPlugError(
            "SWITCHBOT_PLUG_INVALID_PAYLOAD",
            "SwitchBot plug response has no status code.",
            False,
        ) from error
    if isinstance(status_code, bool) or not isinstance(status_code, int):
        raise SwitchBotPlugError(
            "SWITCHBOT_PLUG_INVALID_PAYLOAD",
            "SwitchBot plug response has an invalid status code.",
            False,
        )
    if status_code != 100:
        raise SwitchBotPlugError(
            "SWITCHBOT_PLUG_API_ERROR",
            f"SwitchBot plug API returned status code {status_code}.",
            status_code == 190,
        )


def _validate_device_id(device_id: str) -> None:
    if not isinstance(device_id, str) or not device_id.strip():
        raise SwitchBotPlugError(
            "INVALID_PLUG_DEVICE_ID",
            "Plug device ID must be a non-empty string.",
            False,
        )


def _is_non_negative_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value >= 0
    )
