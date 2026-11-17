"""Ntfy-backed dead-man switch for Raspberry Pi availability."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

import requests

from smart_home_qa_harness.file_state import (
    atomic_write_text,
    exclusive_state_lock,
)
from smart_home_qa_harness.ntfy_notifier import (
    NTFY_TIMEOUT_SECONDS,
    NtfyConfig,
)


HEARTBEAT_SEQUENCE_ID = "smart-home-pi-heartbeat"
DEFAULT_HEARTBEAT_DELAY_SECONDS = 900
DEFAULT_HEARTBEAT_STATE_FILE = "/app/.state/ntfy-heartbeat.json"
_MAXIMUM_DELAY_SECONDS = 3 * 24 * 60 * 60
_TOPIC_PATTERN = re.compile(r"[-_A-Za-z0-9]{1,64}")


class NtfyHeartbeatError(Exception):
    """Stable, redacted failure raised by the heartbeat workflow."""

    def __init__(self, code: str, retryable: bool):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class NtfyHeartbeatConfig:
    ntfy: NtfyConfig
    state_file: Path
    delay_seconds: int = DEFAULT_HEARTBEAT_DELAY_SECONDS
    dashboard_url: str | None = None


@dataclass(frozen=True)
class NtfyHeartbeatState:
    version: int = 1
    paused: bool = False
    last_renewed_at: str | None = None
    deadline_at: str | None = None
    pending_recovery_since: str | None = None


class NtfyHeartbeatClient:
    """Publish, replace, and cancel ntfy heartbeat notifications."""

    def __init__(self, config: NtfyHeartbeatConfig):
        self._config = config

    def schedule_failure(self) -> None:
        payload: dict[str, Any] = {
            "topic": self._config.ntfy.topic,
            "sequence_id": HEARTBEAT_SEQUENCE_ID,
            "title": "Alerta: Raspberry Pi sem heartbeat",
            "message": (
                "O sistema da casa parou de renovar o heartbeat. "
                "As informações do dashboard podem estar desatualizadas."
            ),
            "priority": 5,
            "tags": ["warning", "house"],
            "delay": f"{self._config.delay_seconds}s",
        }
        if self._config.dashboard_url is not None:
            payload["click"] = self._config.dashboard_url
        self._request("post", json=payload)

    def send_recovery(
        self,
        outage_started_at: datetime,
        recovered_at: datetime,
    ) -> None:
        outage_seconds = max(
            0,
            round((recovered_at - outage_started_at).total_seconds()),
        )
        payload: dict[str, Any] = {
            "topic": self._config.ntfy.topic,
            "sequence_id": _recovery_sequence_id(outage_started_at),
            "title": "Recuperação: heartbeat do Raspberry Pi",
            "message": (
                "O Raspberry Pi voltou a renovar o heartbeat.\n"
                f"Indisponibilidade aproximada: {_duration(outage_seconds)}."
            ),
            "priority": 3,
            "tags": ["white_check_mark", "house"],
        }
        if self._config.dashboard_url is not None:
            payload["click"] = self._config.dashboard_url
        self._request("post", json=payload)

    def cancel_failure(self) -> None:
        url = (
            f"{self._config.ntfy.base_url}/"
            f"{self._config.ntfy.topic}/{HEARTBEAT_SEQUENCE_ID}"
        )
        self._request("delete", url=url)

    def _request(
        self,
        method: str,
        *,
        json: Mapping[str, Any] | None = None,
        url: str | None = None,
    ) -> None:
        try:
            response = requests.request(
                method,
                url or f"{self._config.ntfy.base_url}/",
                json=json,
                headers={
                    "Authorization": (
                        f"Bearer {self._config.ntfy.access_token}"
                    ),
                },
                timeout=NTFY_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout as error:
            raise NtfyHeartbeatError("NTFY_HEARTBEAT_TIMEOUT", True) from error
        except requests.exceptions.ConnectionError as error:
            raise NtfyHeartbeatError(
                "NTFY_HEARTBEAT_CONNECTION_ERROR",
                True,
            ) from error
        except requests.exceptions.HTTPError as error:
            status_code = error.response.status_code
            raise NtfyHeartbeatError(
                "NTFY_HEARTBEAT_HTTP_ERROR",
                status_code == 429 or status_code >= 500,
            ) from error


def load_ntfy_heartbeat_config(
    environ: Mapping[str, str],
) -> NtfyHeartbeatConfig | None:
    """Load optional heartbeat configuration without exposing its values."""

    enabled = environ.get("NTFY_HEARTBEAT_ENABLED", "false").strip().lower()
    if enabled in {"", "false"}:
        return None
    ntfy_enabled = environ.get("NTFY_ENABLED", "false").strip().lower()
    if enabled != "true" or ntfy_enabled != "true":
        raise NtfyHeartbeatError("NTFY_HEARTBEAT_CONFIGURATION_INVALID", False)

    try:
        delay_seconds = int(environ.get(
            "NTFY_HEARTBEAT_DELAY_SECONDS",
            str(DEFAULT_HEARTBEAT_DELAY_SECONDS),
        ))
    except ValueError as error:
        raise NtfyHeartbeatError(
            "NTFY_HEARTBEAT_CONFIGURATION_INVALID",
            False,
        ) from error

    ntfy = NtfyConfig(
        base_url=environ.get("NTFY_BASE_URL", "").strip().rstrip("/"),
        topic=environ.get("NTFY_TOPIC", "").strip(),
        access_token=environ.get("NTFY_ACCESS_TOKEN", "").strip(),
    )
    dashboard_url = environ.get("DASHBOARD_URL", "").strip() or None
    state_file = environ.get(
        "NTFY_HEARTBEAT_STATE_FILE",
        DEFAULT_HEARTBEAT_STATE_FILE,
    ).strip()
    if not (
        _valid_ntfy_config(ntfy)
        and 10 <= delay_seconds <= _MAXIMUM_DELAY_SECONDS
        and state_file
        and _valid_dashboard_url(dashboard_url)
    ):
        raise NtfyHeartbeatError("NTFY_HEARTBEAT_CONFIGURATION_INVALID", False)
    return NtfyHeartbeatConfig(
        ntfy=ntfy,
        state_file=Path(state_file),
        delay_seconds=delay_seconds,
        dashboard_url=dashboard_url,
    )


def run_heartbeat(
    config: NtfyHeartbeatConfig,
    action: str = "renew",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Renew, pause, or resume the dead-man switch atomically."""

    current_time = _as_utc(now or datetime.now(timezone.utc))
    client = NtfyHeartbeatClient(config)
    try:
        with exclusive_state_lock(config.state_file):
            state = _load_state(config.state_file)
            if action == "pause":
                if state.paused:
                    return _event("paused", current_time)
                client.cancel_failure()
                _save_state(
                    config.state_file,
                    NtfyHeartbeatState(paused=True),
                )
                return _event("paused", current_time)
            if action not in {"renew", "resume"}:
                raise NtfyHeartbeatError(
                    "NTFY_HEARTBEAT_ACTION_INVALID",
                    False,
                )
            if state.paused and action == "renew":
                return _event("paused", current_time)

            previous_deadline = _parse_datetime(state.deadline_at)
            pending_recovery = _parse_datetime(
                state.pending_recovery_since
            )
            if pending_recovery is None and (
                previous_deadline is not None
                and current_time >= previous_deadline
            ):
                pending_recovery = previous_deadline

            client.schedule_failure()
            deadline = current_time + timedelta(seconds=config.delay_seconds)
            renewed_state = NtfyHeartbeatState(
                paused=False,
                last_renewed_at=current_time.isoformat(),
                deadline_at=deadline.isoformat(),
                pending_recovery_since=(
                    pending_recovery.isoformat()
                    if pending_recovery is not None
                    else None
                ),
            )
            _save_state(config.state_file, renewed_state)

            recovered = False
            if pending_recovery is not None:
                client.send_recovery(pending_recovery, current_time)
                _save_state(
                    config.state_file,
                    NtfyHeartbeatState(
                        paused=False,
                        last_renewed_at=current_time.isoformat(),
                        deadline_at=deadline.isoformat(),
                    ),
                )
                recovered = True
            return _event(
                "renewed",
                current_time,
                deadline=deadline,
                recovery_sent=recovered,
            )
    except NtfyHeartbeatError:
        raise
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise NtfyHeartbeatError(
            "NTFY_HEARTBEAT_STATE_ERROR",
            False,
        ) from error


def _load_state(path: Path) -> NtfyHeartbeatState:
    if not path.exists():
        return NtfyHeartbeatState()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) - {
        "version",
        "paused",
        "last_renewed_at",
        "deadline_at",
        "pending_recovery_since",
    }:
        raise ValueError("invalid heartbeat state")
    state = NtfyHeartbeatState(**value)
    if state.version != 1 or not isinstance(state.paused, bool):
        raise ValueError("invalid heartbeat state")
    for timestamp in (
        state.last_renewed_at,
        state.deadline_at,
        state.pending_recovery_since,
    ):
        _parse_datetime(timestamp)
    return state


def _save_state(path: Path, state: NtfyHeartbeatState) -> None:
    atomic_write_text(path, json.dumps(asdict(state), sort_keys=True))


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("heartbeat timestamps must include a timezone")
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("heartbeat time must include a timezone")
    return value.astimezone(timezone.utc)


def _event(
    status: str,
    timestamp: datetime,
    *,
    deadline: datetime | None = None,
    recovery_sent: bool = False,
) -> dict[str, Any]:
    return {
        "event": "ntfy_heartbeat",
        "status": status,
        "timestamp": timestamp.isoformat(),
        "deadline": deadline.isoformat() if deadline is not None else None,
        "recovery_sent": recovery_sent,
        "error_code": None,
    }


def _valid_ntfy_config(config: NtfyConfig) -> bool:
    parsed_url = urlparse(config.base_url)
    return bool(
        parsed_url.scheme == "https"
        and parsed_url.netloc
        and parsed_url.path in {"", "/"}
        and parsed_url.username is None
        and parsed_url.password is None
        and not parsed_url.params
        and not parsed_url.query
        and not parsed_url.fragment
        and _TOPIC_PATTERN.fullmatch(config.topic)
        and config.access_token
    )


def _valid_dashboard_url(value: str | None) -> bool:
    if value is None:
        return True
    parsed = urlparse(value)
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.netloc
        and parsed.username is None
        and parsed.password is None
    )


def _recovery_sequence_id(outage_started_at: datetime) -> str:
    return f"{HEARTBEAT_SEQUENCE_ID}-recovery-{int(outage_started_at.timestamp())}"


def _duration(seconds: int) -> str:
    minutes = max(1, round(seconds / 60))
    hours, remaining_minutes = divmod(minutes, 60)
    if hours and remaining_minutes:
        return f"{hours}h {remaining_minutes}min"
    if hours:
        return f"{hours}h"
    return f"{remaining_minutes}min"
