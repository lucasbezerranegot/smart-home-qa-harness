"""Persistent notification deduplication adapters."""

from datetime import date, timedelta
import json
from pathlib import Path

from smart_home_qa_harness.file_state import (
    atomic_write_text,
    exclusive_state_lock,
)


DEFAULT_NOTIFICATION_RETENTION_DAYS = 90


class NotificationStoreError(Exception):
    """Structured failure while reading or writing notification state."""

    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class FileNotificationStore:
    """Persist notification keys safely between local container executions."""

    def __init__(
        self,
        path: str | Path,
        retention_days: int = DEFAULT_NOTIFICATION_RETENTION_DAYS,
    ):
        if (
            isinstance(retention_days, bool)
            or not isinstance(retention_days, int)
            or retention_days < 1
        ):
            raise ValueError("retention_days must be a positive integer.")
        self._path = Path(path)
        self._retention_days = retention_days

    def reserve(self, notification_key: str) -> bool:
        """Return True only when the key was not already persisted."""

        try:
            with exclusive_state_lock(self._path):
                notification_keys = self._load()
                retained_keys = self._retained_keys(
                    notification_keys,
                    notification_key,
                )

                if notification_key in retained_keys:
                    if retained_keys != notification_keys:
                        self._save(retained_keys)
                    return False

                retained_keys.add(notification_key)
                self._save(retained_keys)
                return True
        except NotificationStoreError:
            raise
        except OSError as error:
            raise NotificationStoreError(
                code="NOTIFICATION_STATE_WRITE_FAILED",
                message="Unable to lock or persist notification state.",
                retryable=True,
            ) from error

    def _load(self) -> set[str]:
        if not self._path.exists():
            return set()

        try:
            stored_value = json.loads(
                self._path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as error:
            raise NotificationStoreError(
                code="INVALID_NOTIFICATION_STATE",
                message="Unable to read persisted notification state.",
                retryable=False,
            ) from error

        if (
            not isinstance(stored_value, list)
            or not all(isinstance(key, str) for key in stored_value)
        ):
            raise NotificationStoreError(
                code="INVALID_NOTIFICATION_STATE",
                message="Persisted notification state has an invalid format.",
                retryable=False,
            )

        return set(stored_value)

    def _save(self, notification_keys: set[str]) -> None:
        try:
            atomic_write_text(
                self._path,
                json.dumps(sorted(notification_keys)),
            )
        except OSError as error:
            raise NotificationStoreError(
                code="NOTIFICATION_STATE_WRITE_FAILED",
                message="Unable to persist notification state.",
                retryable=True,
            ) from error

    def _retained_keys(
        self,
        notification_keys: set[str],
        reference_key: str,
    ) -> set[str]:
        reference_date = _notification_date(reference_key)
        if reference_date is None:
            return notification_keys
        oldest_retained_date = reference_date - timedelta(
            days=self._retention_days
        )
        return {
            key
            for key in notification_keys
            if (
                (key_date := _notification_date(key)) is None
                or key_date >= oldest_retained_date
            )
        }


def _notification_date(notification_key: str) -> date | None:
    if len(notification_key) < 12 or notification_key[10] != ":":
        return None
    try:
        return date.fromisoformat(notification_key[:10])
    except ValueError:
        return None
