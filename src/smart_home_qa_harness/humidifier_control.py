"""Coordinate one room Meter with one provider-neutral humidifier."""

from dataclasses import dataclass
from datetime import time

from smart_home_qa_harness.humidifier_engine import (
    decide_humidifier_state,
)
from smart_home_qa_harness.humidifier_provider import (
    HumidifierProvider,
    HumidifierProviderError,
    HumidifierProviderStatus,
    HumidifierState,
)
from smart_home_qa_harness.room_config import RoomConfig


@dataclass(frozen=True)
class HumidifierControlResult:
    room_id: str
    provider_name: str
    device_id: str
    relative_humidity: float | None
    previous_state: HumidifierState | None
    desired_state: HumidifierState | None
    reported_state: HumidifierState | None
    command_attempted: bool
    command_succeeded: bool
    dry_run: bool
    state_confirmed: bool
    error_code: str | None = None


def run_humidifier_control(
    room: RoomConfig,
    relative_humidity: float | None,
    current_time: time,
    provider: HumidifierProvider,
    dry_run: bool = True,
    on_below: float = 45.0,
    off_at: float = 50.0,
) -> HumidifierControlResult:
    """Evaluate and optionally apply one humidifier decision."""

    if room.humidifier_provider is None:
        raise ValueError("The room has no humidifier provider configured.")
    _validate_provider_contract(provider)

    try:
        current_status = _validated_status(provider, provider.read_status())
    except HumidifierProviderError as error:
        return _result(
            room=room,
            provider=provider,
            relative_humidity=relative_humidity,
            previous_state=None,
            desired_state=None,
            reported_state=None,
            command_attempted=False,
            command_succeeded=False,
            dry_run=dry_run,
            state_confirmed=False,
            error_code=error.code,
        )

    previous_state = current_status.reported_state or HumidifierState.OFF
    desired_state = decide_humidifier_state(
        relative_humidity=relative_humidity,
        previous_state=previous_state,
        current_time=current_time,
        on_below=on_below,
        off_at=off_at,
    )

    if desired_state is current_status.reported_state:
        return _result(
            room=room,
            provider=provider,
            relative_humidity=relative_humidity,
            previous_state=previous_state,
            desired_state=desired_state,
            reported_state=current_status.reported_state,
            command_attempted=False,
            command_succeeded=False,
            dry_run=dry_run,
            state_confirmed=current_status.state_confirmed,
        )

    if dry_run:
        return _result(
            room=room,
            provider=provider,
            relative_humidity=relative_humidity,
            previous_state=previous_state,
            desired_state=desired_state,
            reported_state=current_status.reported_state,
            command_attempted=False,
            command_succeeded=False,
            dry_run=True,
            state_confirmed=False,
        )

    try:
        provider.set_state(desired_state)
    except HumidifierProviderError as error:
        return _result(
            room=room,
            provider=provider,
            relative_humidity=relative_humidity,
            previous_state=previous_state,
            desired_state=desired_state,
            reported_state=current_status.reported_state,
            command_attempted=True,
            command_succeeded=False,
            dry_run=False,
            state_confirmed=False,
            error_code=error.code,
        )

    try:
        confirmed_status = _validated_status(provider, provider.read_status())
    except HumidifierProviderError as error:
        return _result(
            room=room,
            provider=provider,
            relative_humidity=relative_humidity,
            previous_state=previous_state,
            desired_state=desired_state,
            reported_state=None,
            command_attempted=True,
            command_succeeded=True,
            dry_run=False,
            state_confirmed=False,
            error_code=error.code,
        )

    state_confirmed = (
        confirmed_status.state_confirmed
        and confirmed_status.reported_state is desired_state
    )
    return _result(
        room=room,
        provider=provider,
        relative_humidity=relative_humidity,
        previous_state=previous_state,
        desired_state=desired_state,
        reported_state=confirmed_status.reported_state,
        command_attempted=True,
        command_succeeded=True,
        dry_run=False,
        state_confirmed=state_confirmed,
        error_code=(
            None
            if state_confirmed or not confirmed_status.confirmation_supported
            else "HUMIDIFIER_STATE_NOT_CONFIRMED"
        ),
    )


def _result(
    room: RoomConfig,
    provider: HumidifierProvider,
    relative_humidity: float | None,
    previous_state: HumidifierState | None,
    desired_state: HumidifierState | None,
    reported_state: HumidifierState | None,
    command_attempted: bool,
    command_succeeded: bool,
    dry_run: bool,
    state_confirmed: bool,
    error_code: str | None = None,
) -> HumidifierControlResult:
    return HumidifierControlResult(
        room_id=room.room_id,
        provider_name=provider.provider_name,
        device_id=provider.device_id,
        relative_humidity=relative_humidity,
        previous_state=previous_state,
        desired_state=desired_state,
        reported_state=reported_state,
        command_attempted=command_attempted,
        command_succeeded=command_succeeded,
        dry_run=dry_run,
        state_confirmed=state_confirmed,
        error_code=error_code,
    )


def _validated_status(
    provider: HumidifierProvider,
    status: object,
) -> HumidifierProviderStatus:
    if not isinstance(status, HumidifierProviderStatus):
        raise HumidifierProviderError(
            "INVALID_HUMIDIFIER_PROVIDER_RESULT",
            "Humidifier provider returned an invalid status.",
            False,
        )
    if (
        status.provider_name != provider.provider_name
        or status.device_id != provider.device_id
    ):
        raise HumidifierProviderError(
            "HUMIDIFIER_PROVIDER_MISMATCH",
            "Humidifier provider returned status for another device.",
            False,
        )
    return status


def _validate_provider_contract(provider: object) -> None:
    if (
        not isinstance(getattr(provider, "provider_name", None), str)
        or not getattr(provider, "provider_name").strip()
        or not isinstance(getattr(provider, "device_id", None), str)
        or not getattr(provider, "device_id").strip()
        or not callable(getattr(provider, "read_status", None))
        or not callable(getattr(provider, "set_state", None))
    ):
        raise ValueError("A valid HumidifierProvider is required.")
