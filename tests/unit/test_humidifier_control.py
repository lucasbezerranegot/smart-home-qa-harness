from datetime import time
from unittest.mock import Mock, call

import pytest

from smart_home_qa_harness.humidifier_control import run_humidifier_control
from smart_home_qa_harness.humidifier_provider import (
    HumidifierProviderError,
    HumidifierProviderStatus,
    HumidifierState,
)
from smart_home_qa_harness.room_config import (
    HumidifierProviderKind,
    RoomConfig,
)


ROOM = RoomConfig(
    "bedroom",
    "quarto",
    "meter-bedroom",
    True,
    HumidifierProviderKind.SWITCHBOT_PLUG,
    "plug-bedroom",
)


def status(state, confirmed=True, power=0, confirmation_supported=True):
    return HumidifierProviderStatus(
        provider_name="fake-provider",
        device_id="humidifier-bedroom",
        reported_state=state,
        state_confirmed=confirmed,
        confirmation_supported=confirmation_supported,
        power_watts=power,
    )


def provider(*statuses):
    result = Mock()
    result.provider_name = "fake-provider"
    result.device_id = "humidifier-bedroom"
    result.read_status = Mock(side_effect=statuses)
    result.set_state = Mock()
    return result


@pytest.mark.parametrize(
    "provider_name,confirmation_supported",
    [
        ("switchbot-plug", True),
        ("vesync", True),
        ("unobservable-provider", False),
    ],
)
def test_common_contract_produces_same_decision_for_every_provider(
    provider_name,
    confirmation_supported,
):
    target = provider(
        status(
            HumidifierState.OFF,
            confirmed=confirmation_supported,
            confirmation_supported=confirmation_supported,
        ),
        status(
            HumidifierState.ON,
            confirmed=confirmation_supported,
            confirmation_supported=confirmation_supported,
        ),
    )
    target.provider_name = provider_name
    target.read_status.side_effect = [
        HumidifierProviderStatus(
            provider_name,
            target.device_id,
            HumidifierState.OFF,
            confirmation_supported,
            confirmation_supported,
        ),
        HumidifierProviderStatus(
            provider_name,
            target.device_id,
            HumidifierState.ON,
            confirmation_supported,
            confirmation_supported,
        ),
    ]

    result = run_humidifier(target, humidity=40)

    assert result.desired_state is HumidifierState.ON
    assert result.command_attempted is True
    assert result.command_succeeded is True
    assert result.state_confirmed is confirmation_supported


def test_dry_run_reports_command_without_changing_device():
    target = provider(status(HumidifierState.OFF))

    result = run_humidifier_control(
        ROOM,
        relative_humidity=40,
        current_time=time(20),
        provider=target,
    )

    assert result.previous_state is HumidifierState.OFF
    assert result.desired_state is HumidifierState.ON
    assert result.command_attempted is False
    assert result.command_succeeded is False
    assert result.dry_run is True
    target.set_state.assert_not_called()


def test_applies_and_confirms_turn_on():
    target = provider(
        status(HumidifierState.OFF),
        status(HumidifierState.ON, power=20),
    )

    result = run_humidifier(target, humidity=40)

    target.set_state.assert_called_once_with(HumidifierState.ON)
    assert result.command_attempted is True
    assert result.command_succeeded is True
    assert result.reported_state is HumidifierState.ON
    assert result.state_confirmed is True
    assert result.error_code is None


def test_retries_stale_provider_state_until_command_is_confirmed():
    target = provider(
        status(HumidifierState.OFF),
        status(HumidifierState.OFF),
        status(HumidifierState.OFF),
        status(HumidifierState.ON),
    )
    wait = Mock()

    result = run_humidifier(
        target,
        humidity=40,
        confirmation_retry_delays=(2, 5, 10),
        wait=wait,
    )

    assert result.reported_state is HumidifierState.ON
    assert result.state_confirmed is True
    assert result.error_code is None
    assert target.read_status.call_count == 4
    assert wait.call_args_list == [call(2.0), call(5.0)]


def test_reports_unconfirmed_state_after_all_retries_are_exhausted():
    target = provider(
        status(HumidifierState.OFF),
        status(HumidifierState.OFF),
        status(HumidifierState.OFF),
        status(HumidifierState.OFF),
    )
    wait = Mock()

    result = run_humidifier(
        target,
        humidity=40,
        confirmation_retry_delays=(2, 5),
        wait=wait,
    )

    assert result.error_code == "HUMIDIFIER_STATE_NOT_CONFIRMED"
    assert result.state_confirmed is False
    assert target.read_status.call_count == 4
    assert wait.call_args_list == [call(2.0), call(5.0)]


def test_missing_humidity_turns_running_device_off():
    target = provider(
        status(HumidifierState.ON),
        status(HumidifierState.OFF),
    )

    result = run_humidifier(target, humidity=None)

    target.set_state.assert_called_once_with(HumidifierState.OFF)
    assert result.state_confirmed is True


def test_does_not_send_command_when_reported_state_is_already_correct():
    target = provider(status(HumidifierState.ON))

    result = run_humidifier(target, humidity=40)

    assert result.command_attempted is False
    assert result.state_confirmed is True
    target.set_state.assert_not_called()


def test_preserves_unconfirmed_state_without_claiming_physical_confirmation():
    target = provider(status(HumidifierState.ON, confirmed=False))

    result = run_humidifier(target, humidity=40)

    assert result.command_attempted is False
    assert result.reported_state is HumidifierState.ON
    assert result.state_confirmed is False


def test_unknown_state_uses_safe_off_as_hysteresis_baseline():
    target = provider(
        status(None, confirmed=False),
        status(HumidifierState.OFF, confirmed=False),
    )

    result = run_humidifier(target, humidity=47)

    assert result.previous_state is HumidifierState.OFF
    assert result.desired_state is HumidifierState.OFF
    assert result.state_confirmed is False


def test_returns_structured_error_when_status_cannot_be_read():
    target = provider()
    target.read_status.side_effect = HumidifierProviderError(
        "PROVIDER_OFFLINE",
        "offline",
        True,
    )

    result = run_humidifier(target, humidity=40)

    assert result.error_code == "PROVIDER_OFFLINE"
    assert result.desired_state is None
    assert result.command_attempted is False


def test_reports_command_rejection_separately_from_attempt():
    target = provider(status(HumidifierState.OFF))
    target.set_state.side_effect = HumidifierProviderError(
        "COMMAND_REJECTED",
        "rejected",
        False,
    )

    result = run_humidifier(target, humidity=40)

    assert result.command_attempted is True
    assert result.command_succeeded is False
    assert result.error_code == "COMMAND_REJECTED"


def test_reports_read_after_write_failure_without_losing_command_success():
    target = provider(status(HumidifierState.OFF))
    target.read_status.side_effect = [
        status(HumidifierState.OFF),
        HumidifierProviderError("READ_FAILED", "failed", True),
    ]

    result = run_humidifier(target, humidity=40)

    assert result.command_attempted is True
    assert result.command_succeeded is True
    assert result.state_confirmed is False
    assert result.error_code == "READ_FAILED"


def test_reports_unconfirmed_command():
    target = provider(
        status(HumidifierState.OFF),
        status(HumidifierState.OFF),
    )

    result = run_humidifier(target, humidity=40)

    assert result.error_code == "HUMIDIFIER_STATE_NOT_CONFIRMED"
    assert result.state_confirmed is False


def test_expected_ir_non_confirmation_is_not_reported_as_provider_failure():
    target = provider(
        status(None, confirmed=False, confirmation_supported=False),
        status(
            HumidifierState.ON,
            confirmed=False,
            confirmation_supported=False,
        ),
    )

    wait = Mock()
    result = run_humidifier(
        target,
        humidity=40,
        confirmation_retry_delays=(2, 5),
        wait=wait,
    )

    assert result.command_succeeded is True
    assert result.reported_state is HumidifierState.ON
    assert result.state_confirmed is False
    assert result.error_code is None
    wait.assert_not_called()


@pytest.mark.parametrize(
    "delays",
    ["2,5", (0,), (-1,), (float("nan"),), ("later",)],
)
def test_rejects_invalid_confirmation_retry_delays(delays):
    with pytest.raises(ValueError):
        run_humidifier_control(
            ROOM,
            relative_humidity=40,
            current_time=time(20),
            provider=provider(status(HumidifierState.OFF)),
            confirmation_retry_delays=delays,
        )


@pytest.mark.parametrize(
    "bad_status",
    [
        {"state": "ON"},
        HumidifierProviderStatus(
            "another-provider",
            "humidifier-bedroom",
            HumidifierState.OFF,
            True,
        ),
        HumidifierProviderStatus(
            "fake-provider",
            "another-device",
            HumidifierState.OFF,
            True,
        ),
    ],
)
def test_rejects_malformed_or_mismatched_provider_results_before_command(
    bad_status,
):
    target = provider(bad_status)

    result = run_humidifier(target, humidity=40)

    assert result.command_attempted is False
    assert result.error_code in {
        "INVALID_HUMIDIFIER_PROVIDER_RESULT",
        "HUMIDIFIER_PROVIDER_MISMATCH",
    }
    target.set_state.assert_not_called()


def test_rejects_room_without_humidifier():
    no_humidifier = RoomConfig("living", "sala", "meter", True)

    with pytest.raises(ValueError):
        run_humidifier_control(
            no_humidifier,
            40,
            time(20),
            provider(HumidifierState.OFF),
        )


def run_humidifier(target, humidity, **arguments):
    return run_humidifier_control(
        ROOM,
        relative_humidity=humidity,
        current_time=time(20),
        provider=target,
        dry_run=False,
        **arguments,
    )
