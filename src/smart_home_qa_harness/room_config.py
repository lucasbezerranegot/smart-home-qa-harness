"""Shared room-to-device configuration for home automations."""

from collections.abc import Mapping
from dataclasses import dataclass


class RoomConfigurationError(ValueError):
    """Stable validation failure for room/device configuration."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = False


@dataclass(frozen=True)
class RoomConfig:
    """Devices and capabilities that belong to one physical room."""

    room_id: str
    display_name: str
    meter_id: str
    has_window: bool
    humidifier_plug_id: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("room_id", self.room_id),
            ("display_name", self.display_name),
            ("meter_id", self.meter_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise RoomConfigurationError(
                    "INVALID_ROOM_CONFIGURATION",
                    f"{field_name} must be a non-empty string.",
                )

        if not isinstance(self.has_window, bool):
            raise RoomConfigurationError(
                "INVALID_ROOM_CONFIGURATION",
                "has_window must be a boolean.",
            )

        if self.humidifier_plug_id is not None and (
            not isinstance(self.humidifier_plug_id, str)
            or not self.humidifier_plug_id.strip()
        ):
            raise RoomConfigurationError(
                "INVALID_ROOM_CONFIGURATION",
                "humidifier_plug_id must be null or a non-empty string.",
            )


@dataclass(frozen=True)
class HomeRoomConfig:
    """Validated room registry shared by all controllers."""

    rooms: tuple[RoomConfig, ...]

    def __post_init__(self) -> None:
        if not self.rooms:
            raise RoomConfigurationError(
                "INVALID_ROOM_CONFIGURATION",
                "At least one room must be configured.",
            )

        _reject_duplicates(
            "room ID",
            [room.room_id for room in self.rooms],
        )
        _reject_duplicates(
            "Meter ID",
            [room.meter_id for room in self.rooms],
        )
        _reject_duplicates(
            "humidifier plug ID",
            [
                room.humidifier_plug_id
                for room in self.rooms
                if room.humidifier_plug_id is not None
            ],
        )

    @property
    def ventilation_rooms(self) -> tuple[RoomConfig, ...]:
        return tuple(room for room in self.rooms if room.has_window)

    @property
    def humidifier_rooms(self) -> tuple[RoomConfig, ...]:
        return tuple(
            room
            for room in self.rooms
            if room.humidifier_plug_id is not None
        )


def load_room_config(environ: Mapping[str, str]) -> HomeRoomConfig:
    """Load numbered ``ROOM_*`` entries from an environment mapping."""

    try:
        room_count = int(environ["ROOM_COUNT"])
    except KeyError as error:
        raise RoomConfigurationError(
            "MISSING_ROOM_CONFIGURATION",
            "Missing required configuration: ROOM_COUNT",
        ) from error
    except (TypeError, ValueError) as error:
        raise RoomConfigurationError(
            "INVALID_ROOM_CONFIGURATION",
            "ROOM_COUNT must be a positive integer.",
        ) from error

    if room_count <= 0:
        raise RoomConfigurationError(
            "INVALID_ROOM_CONFIGURATION",
            "ROOM_COUNT must be a positive integer.",
        )

    try:
        rooms = tuple(
            _load_room(environ, index)
            for index in range(1, room_count + 1)
        )
    except KeyError as error:
        raise RoomConfigurationError(
            "MISSING_ROOM_CONFIGURATION",
            f"Missing required configuration: {error.args[0]}",
        ) from error

    return HomeRoomConfig(rooms=rooms)


def _load_room(environ: Mapping[str, str], index: int) -> RoomConfig:
    prefix = f"ROOM_{index}"
    return RoomConfig(
        room_id=environ[f"{prefix}_ID"],
        display_name=environ[f"{prefix}_DISPLAY_NAME"],
        meter_id=environ[f"{prefix}_METER_ID"],
        has_window=_parse_boolean(
            environ[f"{prefix}_HAS_WINDOW"],
            f"{prefix}_HAS_WINDOW",
        ),
        humidifier_plug_id=(
            environ.get(f"{prefix}_HUMIDIFIER_PLUG_ID", "").strip()
            or None
        ),
    )


def _parse_boolean(value: str, key: str) -> bool:
    if not isinstance(value, str) or value.strip().lower() not in {
        "true",
        "false",
    }:
        raise RoomConfigurationError(
            "INVALID_ROOM_CONFIGURATION",
            f"{key} must be true or false.",
        )
    return value.strip().lower() == "true"


def _reject_duplicates(label: str, values: list[str]) -> None:
    if len(values) != len(set(values)):
        raise RoomConfigurationError(
            "DUPLICATE_ROOM_DEVICE",
            f"Each {label} may be assigned only once.",
        )
