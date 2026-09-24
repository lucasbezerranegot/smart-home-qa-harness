"""Coordinate heating decisions with one physical relay channel."""

from collections.abc import Callable
from dataclasses import dataclass

from smart_home_qa_harness.heating_control import (
    HeatingConfiguration,
    decide_relay_state,
)
from smart_home_qa_harness.heating_engine import MeterReading
from smart_home_qa_harness.switchbot_relay_client import (
    RelayChannelStatus,
    RelayState,
    SwitchBotRelayError,
)


@dataclass(frozen=True)
class HeatingOrchestrationResult:
    relay_id: str
    channel: int
    meter_id: str
    previous_state: RelayState | None
    desired_state: RelayState | None
    command_sent: bool
    dry_run: bool
    state_confirmed: bool
    error_code: str | None = None


def run_heating_control(
    configuration: HeatingConfiguration,
    readings: list[MeterReading],
    status_provider: Callable[[str, int], RelayChannelStatus],
    state_setter: Callable[[str, int, RelayState], None],
    dry_run: bool = True,
) -> HeatingOrchestrationResult:
    """Evaluate and optionally apply one heating relay-channel decision."""

    try:
        current_status = status_provider(
            configuration.relay_id,
            configuration.channel,
        )
    except SwitchBotRelayError as error:
        return _result(
            configuration=configuration,
            previous_state=None,
            desired_state=None,
            command_sent=False,
            dry_run=dry_run,
            state_confirmed=False,
            error_code=error.code,
        )

    desired_state = RelayState(
        decide_relay_state(
            configuration=configuration,
            readings=readings,
            previous_state=current_status.state.value,
        )
    )

    if desired_state is current_status.state:
        return _result(
            configuration=configuration,
            previous_state=current_status.state,
            desired_state=desired_state,
            command_sent=False,
            dry_run=dry_run,
            state_confirmed=True,
        )

    if dry_run:
        return _result(
            configuration=configuration,
            previous_state=current_status.state,
            desired_state=desired_state,
            command_sent=False,
            dry_run=True,
            state_confirmed=False,
        )

    try:
        state_setter(
            configuration.relay_id,
            configuration.channel,
            desired_state,
        )
        confirmed_status = status_provider(
            configuration.relay_id,
            configuration.channel,
        )
    except SwitchBotRelayError as error:
        return _result(
            configuration=configuration,
            previous_state=current_status.state,
            desired_state=desired_state,
            command_sent=True,
            dry_run=False,
            state_confirmed=False,
            error_code=error.code,
        )

    state_confirmed = confirmed_status.state is desired_state
    return _result(
        configuration=configuration,
        previous_state=current_status.state,
        desired_state=desired_state,
        command_sent=True,
        dry_run=False,
        state_confirmed=state_confirmed,
        error_code=None if state_confirmed else "RELAY_STATE_NOT_CONFIRMED",
    )


def _result(
    configuration: HeatingConfiguration,
    previous_state: RelayState | None,
    desired_state: RelayState | None,
    command_sent: bool,
    dry_run: bool,
    state_confirmed: bool,
    error_code: str | None = None,
) -> HeatingOrchestrationResult:
    return HeatingOrchestrationResult(
        relay_id=configuration.relay_id,
        channel=configuration.channel,
        meter_id=configuration.meter_id,
        previous_state=previous_state,
        desired_state=desired_state,
        command_sent=command_sent,
        dry_run=dry_run,
        state_confirmed=state_confirmed,
        error_code=error_code,
    )
