"""Versioned operational events and persistent failure alert evaluation."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from smart_home_qa_harness.file_state import (
    atomic_write_text,
    exclusive_state_lock,
)


OPERATIONAL_EVENT_SCHEMA_VERSION = 1
OPERATIONAL_ALERT_STATE_SCHEMA_VERSION = 1
DEFAULT_ALERT_AFTER_CONSECUTIVE_FAILURES = 3


class OperationalAlertStateError(Exception):
    """Stable failure raised when alert state cannot be read or written."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AlertEvaluation:
    status: str
    consecutive_failures: int
    notification_required: bool
    error_code: str | None = None


class FileOperationalAlertTracker:
    """Track active consecutive failures across local executor processes."""

    def __init__(self, path: str | Path, alert_after: int = 3):
        if (
            isinstance(alert_after, bool)
            or not isinstance(alert_after, int)
            or alert_after < 1
        ):
            raise ValueError("alert_after must be a positive integer.")
        self.path = Path(path)
        self.alert_after = alert_after

    def evaluate(
        self,
        subsystem: str,
        scope: str,
        error_code: str | None,
    ) -> AlertEvaluation:
        try:
            with exclusive_state_lock(self.path):
                return self._evaluate_locked(subsystem, scope, error_code)
        except OperationalAlertStateError:
            raise
        except OSError as error:
            raise OperationalAlertStateError(
                "OPERATIONAL_ALERT_STATE_UNAVAILABLE",
                "Operational alert state could not be locked or written.",
            ) from error

    def _evaluate_locked(
        self,
        subsystem: str,
        scope: str,
        error_code: str | None,
    ) -> AlertEvaluation:
        state = self._load()
        entries = state["entries"]
        key = f"{subsystem}:{scope}"
        previous = entries.get(key)

        if error_code is None:
            if previous is None:
                return AlertEvaluation("healthy", 0, False)
            notification_required = bool(previous["alerted"])
            del entries[key]
            self._save(state)
            return AlertEvaluation(
                "recovered" if notification_required else "healthy",
                0,
                notification_required,
            )

        if previous is not None and previous["error_code"] == error_code:
            consecutive_failures = previous["consecutive_failures"] + 1
            already_alerted = previous["alerted"]
        else:
            consecutive_failures = 1
            already_alerted = False

        notification_required = (
            consecutive_failures >= self.alert_after and not already_alerted
        )
        alerted = already_alerted or notification_required
        entries[key] = {
            "error_code": error_code,
            "consecutive_failures": consecutive_failures,
            "alerted": alerted,
        }
        self._save(state)

        if notification_required:
            status = "triggered"
        elif alerted:
            status = "ongoing"
        else:
            status = "pending"
        return AlertEvaluation(
            status,
            consecutive_failures,
            notification_required,
        )

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "schema_version": OPERATIONAL_ALERT_STATE_SCHEMA_VERSION,
                "entries": {},
            }
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise OperationalAlertStateError(
                "OPERATIONAL_ALERT_STATE_UNAVAILABLE",
                "Operational alert state could not be read.",
            ) from error
        if not _valid_state(value):
            raise OperationalAlertStateError(
                "INVALID_OPERATIONAL_ALERT_STATE",
                "Operational alert state has an invalid schema.",
            )
        return value

    def _save(self, state: Mapping[str, Any]) -> None:
        try:
            atomic_write_text(
                self.path,
                json.dumps(state, sort_keys=True),
            )
        except OSError as error:
            raise OperationalAlertStateError(
                "OPERATIONAL_ALERT_STATE_UNAVAILABLE",
                "Operational alert state could not be written.",
            ) from error


def build_operational_event(
    *,
    timestamp: datetime,
    subsystem: str,
    scope_kind: str,
    scope: str,
    decision: str,
    command_status: str,
    confirmation_status: str,
    error_code: str | None,
    alert_tracker: FileOperationalAlertTracker | None = None,
    measurements: Mapping[str, float | None] | None = None,
    state: Mapping[str, str | bool | None] | None = None,
) -> dict[str, Any]:
    """Build a controlled event shape that cannot accept device identifiers."""

    if scope_kind not in {"home", "room", "zone"}:
        raise ValueError("scope_kind must be home, room, or zone.")
    alert = _evaluate_alert_safely(
        alert_tracker,
        subsystem,
        scope,
        error_code,
    )
    event: dict[str, Any] = {
        "schema_version": OPERATIONAL_EVENT_SCHEMA_VERSION,
        "event": "operational_cycle",
        "timestamp": timestamp.isoformat(),
        "subsystem": subsystem,
        scope_kind: scope,
        "decision": decision,
        "command_status": command_status,
        "confirmation_status": confirmation_status,
        "error_code": error_code,
        "alert": {
            "status": alert.status,
            "consecutive_failures": alert.consecutive_failures,
            "notification_required": alert.notification_required,
        },
    }
    if alert.error_code is not None:
        event["observability_error_code"] = alert.error_code
    if measurements:
        event["measurements"] = dict(measurements)
    if state:
        event["state"] = dict(state)
    return event


def load_operational_alert_tracker(
    environ: Mapping[str, str],
) -> FileOperationalAlertTracker | None:
    """Load optional alert persistence without making control depend on it."""

    path = environ.get("OPERATIONAL_ALERT_STATE_FILE", "").strip()
    if not path:
        return None
    try:
        threshold = int(
            environ.get(
                "OPERATIONAL_ALERT_AFTER_CONSECUTIVE_FAILURES",
                str(DEFAULT_ALERT_AFTER_CONSECUTIVE_FAILURES),
            )
        )
        return FileOperationalAlertTracker(path, threshold)
    except (TypeError, ValueError):
        return None


def _evaluate_alert_safely(
    tracker: FileOperationalAlertTracker | None,
    subsystem: str,
    scope: str,
    error_code: str | None,
) -> AlertEvaluation:
    if tracker is None:
        return AlertEvaluation("untracked", 0, False)
    try:
        return tracker.evaluate(subsystem, scope, error_code)
    except OperationalAlertStateError as error:
        return AlertEvaluation("unavailable", 0, False, error.code)
    except Exception:
        return AlertEvaluation(
            "unavailable",
            0,
            False,
            "OPERATIONAL_ALERT_EVALUATION_FAILED",
        )


def _valid_state(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("schema_version") != OPERATIONAL_ALERT_STATE_SCHEMA_VERSION:
        return False
    entries = value.get("entries")
    if not isinstance(entries, dict):
        return False
    return all(_valid_entry(key, entry) for key, entry in entries.items())


def _valid_entry(key: object, entry: object) -> bool:
    return (
        isinstance(key, str)
        and isinstance(entry, dict)
        and isinstance(entry.get("error_code"), str)
        and isinstance(entry.get("consecutive_failures"), int)
        and not isinstance(entry.get("consecutive_failures"), bool)
        and entry["consecutive_failures"] >= 1
        and isinstance(entry.get("alerted"), bool)
    )
