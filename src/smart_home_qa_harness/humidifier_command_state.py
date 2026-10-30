"""Durable pending confirmation state for humidifier commands."""

from dataclasses import dataclass
from datetime import datetime
from contextlib import contextmanager
from collections.abc import Iterator
import json
from pathlib import Path
from typing import Any

from smart_home_qa_harness.file_state import (
    atomic_write_text,
    exclusive_state_lock,
)
from smart_home_qa_harness.humidifier_provider import HumidifierState


SCHEMA_VERSION = 1


class HumidifierCommandStateError(Exception):
    """Stable error raised when pending command state is unavailable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PendingHumidifierCommand:
    desired_state: HumidifierState
    reserved_at: datetime
    confirmation_deadline: datetime


class FileHumidifierCommandStore:
    """Persist at-most-once humidifier command intents by logical room."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def get(self, room_id: str) -> PendingHumidifierCommand | None:
        with self._locked():
            entry = self._load()["entries"].get(room_id)
            return None if entry is None else _pending_from_entry(entry)

    def reserve(
        self,
        room_id: str,
        desired_state: HumidifierState,
        reserved_at: datetime,
        confirmation_deadline: datetime,
    ) -> None:
        with self._locked():
            state = self._load()
            state["entries"][room_id] = {
                "desired_state": desired_state.value,
                "reserved_at": reserved_at.isoformat(),
                "confirmation_deadline": confirmation_deadline.isoformat(),
            }
            self._save(state)

    def clear(self, room_id: str) -> None:
        with self._locked():
            state = self._load()
            if state["entries"].pop(room_id, None) is not None:
                self._save(state)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        try:
            with exclusive_state_lock(self.path):
                yield
        except HumidifierCommandStateError:
            raise
        except OSError as error:
            raise HumidifierCommandStateError(
                "HUMIDIFIER_COMMAND_STATE_UNAVAILABLE",
                "Humidifier command state could not be locked.",
            ) from error

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": SCHEMA_VERSION, "entries": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise HumidifierCommandStateError(
                "HUMIDIFIER_COMMAND_STATE_UNAVAILABLE",
                "Humidifier command state could not be read.",
            ) from error
        if not _valid_state(value):
            raise HumidifierCommandStateError(
                "INVALID_HUMIDIFIER_COMMAND_STATE",
                "Humidifier command state has an invalid schema.",
            )
        return value

    def _save(self, state: dict[str, Any]) -> None:
        try:
            atomic_write_text(self.path, json.dumps(state, sort_keys=True))
        except OSError as error:
            raise HumidifierCommandStateError(
                "HUMIDIFIER_COMMAND_STATE_UNAVAILABLE",
                "Humidifier command state could not be written.",
            ) from error


def _valid_state(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("schema_version") != SCHEMA_VERSION:
        return False
    entries = value.get("entries")
    if not isinstance(entries, dict):
        return False
    try:
        return all(
            isinstance(room_id, str)
            and bool(room_id)
            and _pending_from_entry(entry) is not None
            for room_id, entry in entries.items()
        )
    except (KeyError, TypeError, ValueError):
        return False


def _pending_from_entry(entry: object) -> PendingHumidifierCommand:
    if not isinstance(entry, dict):
        raise ValueError("Pending command entry must be an object.")
    desired_state = HumidifierState(entry["desired_state"])
    reserved_at = datetime.fromisoformat(entry["reserved_at"])
    confirmation_deadline = datetime.fromisoformat(
        entry["confirmation_deadline"]
    )
    if (
        reserved_at.tzinfo is None
        or confirmation_deadline.tzinfo is None
        or confirmation_deadline <= reserved_at
    ):
        raise ValueError("Pending command timestamps are invalid.")
    return PendingHumidifierCommand(
        desired_state,
        reserved_at,
        confirmation_deadline,
    )
