"""Persistent notification deduplication adapters."""

import json
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError


class NotificationStoreError(Exception):
    """Structured failure while reading or writing notification state."""

    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class FileNotificationStore:
    """Persist notification keys in a JSON file between workflow runs."""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def reserve(self, notification_key: str) -> bool:
        """Return True only when the key was not already persisted."""

        notification_keys = self._load()

        if notification_key in notification_keys:
            return False

        notification_keys.add(notification_key)
        self._save(notification_keys)
        return True

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
        temporary_path = self._path.with_suffix(
            f"{self._path.suffix}.tmp"
        )

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps(sorted(notification_keys)),
                encoding="utf-8",
            )
            temporary_path.replace(self._path)
        except OSError as error:
            raise NotificationStoreError(
                code="NOTIFICATION_STATE_WRITE_FAILED",
                message="Unable to persist notification state.",
                retryable=True,
            ) from error


class DynamoDBNotificationStore:
    """Reserve notification-period keys in a DynamoDB table."""

    def __init__(self, table: Any):
        """Receive the DynamoDB table as an injected dependency."""
        self._table = table

    def reserve(
        self,
        notification_key: str,
        expires_at: int,
    ) -> bool:
        """Return True only when this execution reserves a new key."""

        try:
            self._table.put_item(
                Item={
                    "notification_key": notification_key,
                    "expires_at": expires_at,
                },
                ConditionExpression=(
                    "attribute_not_exists(notification_key)"
                ),
            )
        except ClientError as error:
            error_code = (
                error.response
                .get("Error", {})
                .get("Code")
            )

            if error_code == "ConditionalCheckFailedException":
                return False

            raise

        return True
