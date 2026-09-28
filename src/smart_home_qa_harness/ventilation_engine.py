"""Room-aware ventilation decisions and household aggregation."""

from dataclasses import dataclass
from datetime import time
from enum import Enum

from smart_home_qa_harness.decision_engine import (
    SUMMER_COMFORT_TEMPERATURE,
    WindowAction,
    decide_window_action,
)
from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentData,
)
from smart_home_qa_harness.room_config import RoomConfig


class VentilationReason(Enum):
    SUMMER_COOLING = "SUMMER_COOLING"
    SUMMER_HEAT_PROTECTION = "SUMMER_HEAT_PROTECTION"
    HIGH_HUMIDITY = "HIGH_HUMIDITY"
    NO_RULE_MATCHED = "NO_RULE_MATCHED"


@dataclass(frozen=True)
class RoomVentilationDecision:
    room: RoomConfig
    action: WindowAction
    reason: VentilationReason
    temperature: float
    relative_humidity: float


@dataclass(frozen=True)
class VentilationRecommendation:
    """One action that can mention one or more rooms in one notification."""

    action: WindowAction
    rooms: tuple[RoomConfig, ...]


def decide_room_ventilation(
    room: RoomConfig,
    reading: IndoorEnvironmentData,
    outside_temperature: float,
    daily_max_temperature: float,
    current_time: time,
) -> RoomVentilationDecision:
    """Evaluate one room while retaining the room identity in the result."""

    if not room.has_window:
        raise ValueError("Ventilation decisions require a room with a window.")
    if reading.relative_humidity is None:
        raise ValueError("Ventilation decisions require a humidity reading.")
    if reading.source != f"switchbot:{room.meter_id}":
        raise ValueError("The indoor reading does not belong to this room.")

    action = decide_window_action(
        outside_temperature=outside_temperature,
        inside_temperature=reading.temperature,
        daily_max_temperature=daily_max_temperature,
        relative_humidity=reading.relative_humidity,
        current_time=current_time,
    )

    if action is WindowAction.NO_ACTION:
        reason = VentilationReason.NO_RULE_MATCHED
    elif daily_max_temperature < SUMMER_COMFORT_TEMPERATURE:
        reason = VentilationReason.HIGH_HUMIDITY
    elif action is WindowAction.OPEN_WINDOWS:
        reason = VentilationReason.SUMMER_COOLING
    else:
        reason = VentilationReason.SUMMER_HEAT_PROTECTION

    return RoomVentilationDecision(
        room=room,
        action=action,
        reason=reason,
        temperature=reading.temperature,
        relative_humidity=reading.relative_humidity,
    )


def aggregate_ventilation_decisions(
    decisions: tuple[RoomVentilationDecision, ...],
) -> tuple[VentilationRecommendation, ...]:
    """Group all actionable rooms by action without depending on read order."""

    return tuple(
        VentilationRecommendation(
            action=action,
            rooms=tuple(
                decision.room
                for decision in decisions
                if decision.action is action
            ),
        )
        for action in (
            WindowAction.OPEN_WINDOWS,
            WindowAction.CLOSE_WINDOWS,
        )
        if any(decision.action is action for decision in decisions)
    )
