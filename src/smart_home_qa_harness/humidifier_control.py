"""Coordinate one room Meter with one SwitchBot humidifier plug."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import time

from smart_home_qa_harness.humidifier_engine import (
    decide_humidifier_state,
)
from smart_home_qa_harness.room_config import RoomConfig
from smart_home_qa_harness.switchbot_plug_client import (
    PlugMiniStatus,
    PlugState,
    SwitchBotPlugError,
)


@dataclass(frozen=True)
class HumidifierControlResult:
    room_id: str
    plug_id: str
    relative_humidity: float | None
    previous_state: PlugState | None
    desired_state: PlugState | None
    command_sent: bool
    dry_run: bool
    state_confirmed: bool
    measured_power: float | None
    error_code: str | None = None


def run_humidifier_control(
    room: RoomConfig,
    relative_humidity: float | None,
    current_time: time,
    status_provider: Callable[[str], PlugMiniStatus],
    state_setter: Callable[[str, PlugState], None],
    dry_run: bool = True,
    on_below: float = 45.0,
    off_at: float = 50.0,
) -> HumidifierControlResult:
    """Evaluate and optionally apply one humidifier decision."""

    if room.humidifier_plug_id is None:
        raise ValueError("The room has no humidifier plug configured.")
    plug_id = room.humidifier_plug_id

    try:
        current_status = status_provider(plug_id)
    except SwitchBotPlugError as error:
        return _result(
            room=room,
            relative_humidity=relative_humidity,
            previous_state=None,
            desired_state=None,
            command_sent=False,
            dry_run=dry_run,
            state_confirmed=False,
            measured_power=None,
            error_code=error.code,
        )

    desired_state = decide_humidifier_state(
        relative_humidity=relative_humidity,
        previous_state=current_status.state,
        current_time=current_time,
        on_below=on_below,
        off_at=off_at,
    )

    if desired_state is current_status.state:
        return _result(
            room=room,
            relative_humidity=relative_humidity,
            previous_state=current_status.state,
            desired_state=desired_state,
            command_sent=False,
            dry_run=dry_run,
            state_confirmed=True,
            measured_power=current_status.power,
        )

    if dry_run:
        return _result(
            room=room,
            relative_humidity=relative_humidity,
            previous_state=current_status.state,
            desired_state=desired_state,
            command_sent=False,
            dry_run=True,
            state_confirmed=False,
            measured_power=current_status.power,
        )

    try:
        state_setter(plug_id, desired_state)
        confirmed_status = status_provider(plug_id)
    except SwitchBotPlugError as error:
        return _result(
            room=room,
            relative_humidity=relative_humidity,
            previous_state=current_status.state,
            desired_state=desired_state,
            command_sent=True,
            dry_run=False,
            state_confirmed=False,
            measured_power=current_status.power,
            error_code=error.code,
        )

    state_confirmed = confirmed_status.state is desired_state
    return _result(
        room=room,
        relative_humidity=relative_humidity,
        previous_state=current_status.state,
        desired_state=desired_state,
        command_sent=True,
        dry_run=False,
        state_confirmed=state_confirmed,
        measured_power=confirmed_status.power,
        error_code=(
            None if state_confirmed else "PLUG_STATE_NOT_CONFIRMED"
        ),
    )


def _result(
    room: RoomConfig,
    relative_humidity: float | None,
    previous_state: PlugState | None,
    desired_state: PlugState | None,
    command_sent: bool,
    dry_run: bool,
    state_confirmed: bool,
    measured_power: float | None,
    error_code: str | None = None,
) -> HumidifierControlResult:
    assert room.humidifier_plug_id is not None
    return HumidifierControlResult(
        room_id=room.room_id,
        plug_id=room.humidifier_plug_id,
        relative_humidity=relative_humidity,
        previous_state=previous_state,
        desired_state=desired_state,
        command_sent=command_sent,
        dry_run=dry_run,
        state_confirmed=state_confirmed,
        measured_power=measured_power,
        error_code=error_code,
    )
