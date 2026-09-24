from unittest.mock import Mock

from smart_home_qa_harness.heating_control import HeatingConfiguration
from smart_home_qa_harness.heating_engine import (
    MeterReading,
    MeterReadingStatus,
)
from smart_home_qa_harness.heating_orchestrator import run_heating_control
from smart_home_qa_harness.switchbot_relay_client import (
    RelayChannelStatus,
    RelayState,
    SwitchBotRelayError,
)


def configuration():
    return HeatingConfiguration(
        relay_id="relay-3",
        channel=2,
        meter_id="children-room-meter",
        target_temperature=20.0,
        hysteresis=0.5,
    )


def reading(temperature):
    return MeterReading(
        meter_id="children-room-meter",
        temperature=temperature,
        status=MeterReadingStatus.VALID,
    )


def relay_status(state):
    return RelayChannelStatus(
        device_id="relay-3",
        channel=2,
        state=state,
        online=True,
    )


def test_dry_run_reports_off_decision_without_commanding_relay():
    status_provider = Mock(return_value=relay_status(RelayState.ON))
    state_setter = Mock()

    result = run_heating_control(
        configuration=configuration(),
        readings=[reading(22.0)],
        status_provider=status_provider,
        state_setter=state_setter,
    )

    assert result.previous_state is RelayState.ON
    assert result.desired_state is RelayState.OFF
    assert result.command_sent is False
    assert result.dry_run is True
    assert result.state_confirmed is False
    assert result.error_code is None
    state_setter.assert_not_called()


def test_sends_off_command_and_confirms_new_state():
    status_provider = Mock(
        side_effect=[
            relay_status(RelayState.ON),
            relay_status(RelayState.OFF),
        ]
    )
    state_setter = Mock()

    result = run_heating_control(
        configuration=configuration(),
        readings=[reading(22.0)],
        status_provider=status_provider,
        state_setter=state_setter,
        dry_run=False,
        sleep=lambda _: None,
    )

    state_setter.assert_called_once_with("relay-3", 2, RelayState.OFF)
    assert result.command_sent is True
    assert result.state_confirmed is True
    assert result.error_code is None


def test_does_not_send_command_when_relay_already_has_desired_state():
    status_provider = Mock(return_value=relay_status(RelayState.OFF))
    state_setter = Mock()

    result = run_heating_control(
        configuration=configuration(),
        readings=[reading(22.0)],
        status_provider=status_provider,
        state_setter=state_setter,
        dry_run=False,
    )

    assert result.command_sent is False
    assert result.state_confirmed is True
    state_setter.assert_not_called()


def test_reports_error_when_command_success_is_not_confirmed():
    status_provider = Mock(return_value=relay_status(RelayState.ON))

    result = run_heating_control(
        configuration=configuration(),
        readings=[reading(22.0)],
        status_provider=status_provider,
        state_setter=Mock(),
        dry_run=False,
        sleep=lambda _: None,
    )

    assert result.command_sent is True
    assert result.state_confirmed is False
    assert result.error_code == "RELAY_STATE_NOT_CONFIRMED"


def test_retries_confirmation_without_resending_command():
    status_provider = Mock(
        side_effect=[
            relay_status(RelayState.ON),
            relay_status(RelayState.ON),
            relay_status(RelayState.OFF),
        ]
    )
    state_setter = Mock()
    sleep = Mock()

    result = run_heating_control(
        configuration=configuration(),
        readings=[reading(22.0)],
        status_provider=status_provider,
        state_setter=state_setter,
        dry_run=False,
        sleep=sleep,
    )

    state_setter.assert_called_once_with("relay-3", 2, RelayState.OFF)
    assert status_provider.call_count == 3
    sleep.assert_called_once_with(1.0)
    assert result.command_sent is True
    assert result.state_confirmed is True
    assert result.error_code is None


def test_does_not_command_when_current_relay_state_cannot_be_read():
    status_provider = Mock(
        side_effect=SwitchBotRelayError(
            code="SWITCHBOT_RELAY_TIMEOUT",
            message="Timed out.",
            retryable=True,
        )
    )
    state_setter = Mock()

    result = run_heating_control(
        configuration=configuration(),
        readings=[reading(22.0)],
        status_provider=status_provider,
        state_setter=state_setter,
        dry_run=False,
    )

    assert result.desired_state is None
    assert result.command_sent is False
    assert result.error_code == "SWITCHBOT_RELAY_TIMEOUT"
    state_setter.assert_not_called()
