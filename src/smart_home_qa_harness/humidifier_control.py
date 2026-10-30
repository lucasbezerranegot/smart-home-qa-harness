"""Coordinate one room Meter with one provider-neutral humidifier."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
import math
from time import sleep

from smart_home_qa_harness.humidifier_engine import (
    decide_humidifier_state,
)
from smart_home_qa_harness.humidifier_command_state import (
    FileHumidifierCommandStore,
    HumidifierCommandStateError,
    PendingHumidifierCommand,
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
    confirmation_pending: bool = False
    error_code: str | None = None


def run_humidifier_control(
    room: RoomConfig,
    relative_humidity: float | None,
    current_time: time,
    provider: HumidifierProvider,
    dry_run: bool = True,
    on_below: float = 45.0,
    off_at: float = 50.0,
    confirmation_retry_delays: Sequence[float] = (),
    wait: Callable[[float], None] = sleep,
    pending_command_store: FileHumidifierCommandStore | None = None,
    current_datetime: datetime | None = None,
    confirmation_deadline_seconds: float = 600,
) -> HumidifierControlResult:
    """Evaluate and optionally apply one humidifier decision."""

    if room.humidifier_provider is None:
        raise ValueError("The room has no humidifier provider configured.")
    _validate_provider_contract(provider)
    retry_delays = _validated_retry_delays(confirmation_retry_delays)
    if not callable(wait):
        raise ValueError("wait must be callable.")
    if pending_command_store is not None:
        if current_datetime is None or current_datetime.tzinfo is None:
            raise ValueError(
                "current_datetime must be timezone-aware with pending state."
            )
        if (
            isinstance(confirmation_deadline_seconds, bool)
            or not isinstance(confirmation_deadline_seconds, (int, float))
            or not math.isfinite(confirmation_deadline_seconds)
            or confirmation_deadline_seconds <= 0
        ):
            raise ValueError(
                "confirmation_deadline_seconds must be positive and finite."
            )

    pending = _load_pending(room, provider, pending_command_store)
    if isinstance(pending, HumidifierCommandStateError):
        return _result(
            room, provider, relative_humidity, None, None, None,
            False, False, dry_run, False, error_code=pending.code,
        )

    try:
        current_status = _validated_status(provider, provider.read_status())
    except HumidifierProviderError as error:
        if pending is not None and current_datetime is not None:
            return _pending_result(
                room=room,
                provider=provider,
                relative_humidity=relative_humidity,
                pending=pending,
                reported_state=None,
                current_datetime=current_datetime,
                dry_run=dry_run,
            )
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

    if pending is not None and current_datetime is not None:
        if (
            current_status.state_confirmed
            and current_status.reported_state is pending.desired_state
        ):
            state_error = (
                None
                if dry_run
                else _clear_pending(
                    room, provider, pending_command_store
                )
            )
            if state_error is not None:
                return _result(
                    room, provider, relative_humidity, previous_state,
                    desired_state, current_status.reported_state,
                    False, False, dry_run, False,
                    error_code=state_error.code,
                )
        elif desired_state is pending.desired_state:
            return _pending_result(
                room=room,
                provider=provider,
                relative_humidity=relative_humidity,
                pending=pending,
                reported_state=current_status.reported_state,
                current_datetime=current_datetime,
                dry_run=dry_run,
                previous_state=previous_state,
            )
        else:
            state_error = (
                None
                if dry_run
                else _clear_pending(
                    room, provider, pending_command_store
                )
            )
            if state_error is not None:
                return _result(
                    room, provider, relative_humidity, previous_state,
                    desired_state, current_status.reported_state,
                    False, False, dry_run, False,
                    error_code=state_error.code,
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

    uses_deferred_confirmation = (
        pending_command_store is not None
        and current_datetime is not None
        and provider.provider_name == "vesync"
    )
    if uses_deferred_confirmation:
        try:
            pending_command_store.reserve(
                room.room_id,
                desired_state,
                current_datetime,
                current_datetime + timedelta(
                    seconds=confirmation_deadline_seconds
                ),
            )
        except HumidifierCommandStateError as error:
            return _result(
                room, provider, relative_humidity, previous_state,
                desired_state, current_status.reported_state,
                False, False, False, False, error_code=error.code,
            )

    try:
        provider.set_state(desired_state)
    except HumidifierProviderError as error:
        if uses_deferred_confirmation and error.code in {
            "VESYNC_COMMAND_REJECTED",
            "INVALID_HUMIDIFIER_STATE",
        }:
            state_error = _clear_pending(
                room, provider, pending_command_store
            )
            if state_error is not None:
                error = state_error
        # The outcome of a transport failure can be ambiguous. A durable
        # reservation prevents a blind duplicate command on the next cycle.
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

    if uses_deferred_confirmation:
        return _result(
            room=room,
            provider=provider,
            relative_humidity=relative_humidity,
            previous_state=previous_state,
            desired_state=desired_state,
            reported_state=current_status.reported_state,
            command_attempted=True,
            command_succeeded=True,
            dry_run=False,
            state_confirmed=False,
            confirmation_pending=True,
        )

    try:
        confirmed_status = _read_until_confirmed(
            provider=provider,
            desired_state=desired_state,
            retry_delays=retry_delays,
            wait=wait,
        )
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


def _read_until_confirmed(
    provider: HumidifierProvider,
    desired_state: HumidifierState,
    retry_delays: tuple[float, ...],
    wait: Callable[[float], None],
) -> HumidifierProviderStatus:
    status = _validated_status(provider, provider.read_status())
    if _matches_desired_state(status, desired_state):
        return status

    for delay in retry_delays:
        if not status.confirmation_supported:
            break
        wait(delay)
        status = _validated_status(provider, provider.read_status())
        if _matches_desired_state(status, desired_state):
            break
    return status


def _matches_desired_state(
    status: HumidifierProviderStatus,
    desired_state: HumidifierState,
) -> bool:
    return status.state_confirmed and status.reported_state is desired_state


def _validated_retry_delays(
    retry_delays: Sequence[float],
) -> tuple[float, ...]:
    if isinstance(retry_delays, (str, bytes)):
        raise ValueError("confirmation_retry_delays must contain numbers.")
    try:
        validated = tuple(float(delay) for delay in retry_delays)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "confirmation_retry_delays must contain numbers."
        ) from error
    if any(
        not math.isfinite(delay) or delay <= 0 for delay in validated
    ):
        raise ValueError(
            "confirmation_retry_delays must contain positive finite numbers."
        )
    return validated


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
    confirmation_pending: bool = False,
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
        confirmation_pending=confirmation_pending,
        error_code=error_code,
    )


def _load_pending(room, provider, store):
    if store is None or provider.provider_name != "vesync":
        return None
    try:
        return store.get(room.room_id)
    except HumidifierCommandStateError as error:
        return error


def _clear_pending(room, provider, store):
    if store is None or provider.provider_name != "vesync":
        return None
    try:
        store.clear(room.room_id)
    except HumidifierCommandStateError as error:
        return error
    return None


def _pending_result(
    *,
    room,
    provider,
    relative_humidity,
    pending: PendingHumidifierCommand,
    reported_state,
    current_datetime: datetime,
    dry_run: bool,
    previous_state=None,
):
    expired = current_datetime >= pending.confirmation_deadline
    return _result(
        room=room,
        provider=provider,
        relative_humidity=relative_humidity,
        previous_state=previous_state,
        desired_state=pending.desired_state,
        reported_state=reported_state,
        command_attempted=False,
        command_succeeded=True,
        dry_run=dry_run,
        state_confirmed=False,
        confirmation_pending=not expired,
        error_code=(
            "HUMIDIFIER_STATE_NOT_CONFIRMED" if expired else None
        ),
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
