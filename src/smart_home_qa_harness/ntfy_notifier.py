"""Authenticated ntfy delivery for operational alerts."""

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlparse

import requests


NTFY_TIMEOUT_SECONDS = 5
_TOPIC_PATTERN = re.compile(r"[-_A-Za-z0-9]{1,64}")


class NtfyNotificationError(Exception):
    """Stable redacted failure raised by the ntfy adapter."""

    def __init__(self, code: str, retryable: bool):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class NtfyConfig:
    base_url: str
    topic: str
    access_token: str


class NtfyNotifier:
    """Publish one operational transition through the ntfy JSON API."""

    def __init__(
        self,
        config: NtfyConfig | None,
        configuration_error_code: str | None = None,
    ):
        self._config = config
        self._configuration_error_code = configuration_error_code

    def send(self, event: Mapping[str, Any]) -> None:
        if self._config is None:
            raise NtfyNotificationError(
                self._configuration_error_code
                or "NTFY_CONFIGURATION_INVALID",
                False,
            )
        payload = _build_payload(event, self._config.topic)
        try:
            response = requests.post(
                f"{self._config.base_url}/",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._config.access_token}",
                },
                timeout=NTFY_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout as error:
            raise NtfyNotificationError("NTFY_TIMEOUT", True) from error
        except requests.exceptions.ConnectionError as error:
            raise NtfyNotificationError(
                "NTFY_CONNECTION_ERROR",
                True,
            ) from error
        except requests.exceptions.HTTPError as error:
            status_code = error.response.status_code
            raise NtfyNotificationError(
                "NTFY_HTTP_ERROR",
                status_code == 429 or status_code >= 500,
            ) from error


def load_ntfy_notifier(
    environ: Mapping[str, str],
) -> NtfyNotifier | None:
    """Load optional ntfy delivery without exposing configuration values."""

    enabled = environ.get("NTFY_ENABLED", "false").strip().lower()
    if enabled == "false" or not enabled:
        return None
    if enabled != "true":
        return NtfyNotifier(None, "NTFY_CONFIGURATION_INVALID")

    config = NtfyConfig(
        base_url=environ.get("NTFY_BASE_URL", "").strip().rstrip("/"),
        topic=environ.get("NTFY_TOPIC", "").strip(),
        access_token=environ.get("NTFY_ACCESS_TOKEN", "").strip(),
    )
    if not _valid_config(config):
        return NtfyNotifier(None, "NTFY_CONFIGURATION_INVALID")
    return NtfyNotifier(config)


def _valid_config(config: NtfyConfig) -> bool:
    parsed_url = urlparse(config.base_url)
    return bool(
        parsed_url.scheme == "https"
        and parsed_url.netloc
        and parsed_url.path in {"", "/"}
        and not parsed_url.params
        and not parsed_url.query
        and not parsed_url.fragment
        and parsed_url.username is None
        and parsed_url.password is None
        and _TOPIC_PATTERN.fullmatch(config.topic)
        and config.access_token
    )


def _build_payload(
    event: Mapping[str, Any],
    topic: str,
) -> dict[str, Any]:
    alert = event["alert"]
    subsystem = str(event["subsystem"])
    scope = _event_scope(event)
    timestamp = str(event["timestamp"])
    subsystem_label = _subsystem_label(subsystem)

    if alert["status"] == "recovered":
        return {
            "topic": topic,
            "title": f"Recuperação: {subsystem_label} — {scope}",
            "message": (
                "O subsistema voltou a operar normalmente.\n"
                f"Horário: {timestamp}"
            ),
            "priority": 3,
            "tags": ["white_check_mark", "house"],
        }

    return {
        "topic": topic,
        "title": f"Falha: {subsystem_label} — {scope}",
        "message": (
            f"Código: {event['error_code']}\n"
            f"Falhas consecutivas: {alert['consecutive_failures']}\n"
            f"Horário: {timestamp}"
        ),
        "priority": 4,
        "tags": ["warning", "house"],
    }


def _event_scope(event: Mapping[str, Any]) -> str:
    for scope_kind in ("zone", "room", "home"):
        if scope_kind in event:
            return str(event[scope_kind])
    return "home"


def _subsystem_label(subsystem: str) -> str:
    return {
        "heating": "Aquecimento",
        "humidifier": "Umidificação",
        "ventilation": "Ventilação",
        "environment_reading": "Sensor ambiental",
        "weather": "Meteorologia",
        "room_control": "Controle dos cômodos",
    }.get(subsystem, subsystem)
