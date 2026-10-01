"""Coordinate ventilation decisions across all rooms with windows."""

from dataclasses import dataclass
from datetime import time

from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentData,
)
from smart_home_qa_harness.room_config import HomeRoomConfig
from smart_home_qa_harness.ventilation_engine import (
    RoomVentilationDecision,
    VentilationRecommendation,
    aggregate_ventilation_decisions,
    decide_room_ventilation,
)


@dataclass(frozen=True)
class RoomVentilationFailure:
    room_id: str
    error_code: str


@dataclass(frozen=True)
class HomeVentilationResult:
    decisions: tuple[RoomVentilationDecision, ...]
    recommendations: tuple[VentilationRecommendation, ...]
    failures: tuple[RoomVentilationFailure, ...]


def evaluate_home_ventilation(
    home: HomeRoomConfig,
    readings: dict[str, IndoorEnvironmentData],
    outside_temperature: float,
    daily_max_temperature: float,
    current_time: time,
) -> HomeVentilationResult:
    """Evaluate every available window room before aggregating any action."""

    decisions: list[RoomVentilationDecision] = []
    failures: list[RoomVentilationFailure] = []

    for room in home.ventilation_rooms:
        reading = readings.get(room.room_id)
        if reading is None:
            failures.append(
                RoomVentilationFailure(
                    room_id=room.room_id,
                    error_code="MISSING_ROOM_READING",
                )
            )
            continue

        try:
            decisions.append(
                decide_room_ventilation(
                    room=room,
                    reading=reading,
                    outside_temperature=outside_temperature,
                    daily_max_temperature=daily_max_temperature,
                    current_time=current_time,
                )
            )
        except ValueError:
            failures.append(
                RoomVentilationFailure(
                    room_id=room.room_id,
                    error_code="INVALID_ROOM_READING",
                )
            )

    immutable_decisions = tuple(decisions)
    return HomeVentilationResult(
        decisions=immutable_decisions,
        recommendations=aggregate_ventilation_decisions(
            immutable_decisions
        ),
        failures=tuple(failures),
    )
