from datetime import time
from unittest.mock import Mock

import pytest

from smart_home_qa_harness.humidifier_control import run_humidifier_control
from smart_home_qa_harness.room_config import RoomConfig
from smart_home_qa_harness.switchbot_plug_client import (
    PlugMiniStatus,
    PlugState,
    SwitchBotPlugError,
)


ROOM = RoomConfig(
    "bedroom",
    "quarto",
    "meter-bedroom",
    True,
    "plug-bedroom",
)


def status(state, power=0):
    return PlugMiniStatus(
        device_id="plug-bedroom",
        state=state,
        voltage=230,
        power=power,
        electric_current=0,
        used_electricity=0,
    )


def test_dry_run_reports_command_without_changing_plug():
    provider = Mock(return_value=status(PlugState.OFF))
    setter = Mock()

    result = run_humidifier_control(
        ROOM,
        relative_humidity=40,
        current_time=time(20),
        status_provider=provider,
        state_setter=setter,
    )

    assert result.previous_state is PlugState.OFF
    assert result.desired_state is PlugState.ON
    assert result.command_sent is False
    assert result.dry_run is True
    setter.assert_not_called()


def test_applies_and_confirms_turn_on():
    provider = Mock(
        side_effect=[status(PlugState.OFF), status(PlugState.ON, power=20)]
    )
    setter = Mock()

    result = run_humidifier_control(
        ROOM,
        relative_humidity=40,
        current_time=time(20),
        status_provider=provider,
        state_setter=setter,
        dry_run=False,
    )

    setter.assert_called_once_with("plug-bedroom", PlugState.ON)
    assert result.command_sent is True
    assert result.state_confirmed is True
    assert result.measured_power == 20
    # Power is deliberately recorded, not classified as water/no-water.
    assert result.error_code is None


def test_missing_humidity_turns_running_plug_off():
    provider = Mock(
        side_effect=[status(PlugState.ON, 20), status(PlugState.OFF)]
    )
    setter = Mock()

    result = run_humidifier_control(
        ROOM,
        relative_humidity=None,
        current_time=time(20),
        status_provider=provider,
        state_setter=setter,
        dry_run=False,
    )

    setter.assert_called_once_with("plug-bedroom", PlugState.OFF)
    assert result.state_confirmed is True


def test_does_not_send_command_when_state_is_already_correct():
    setter = Mock()

    result = run_humidifier_control(
        ROOM,
        relative_humidity=40,
        current_time=time(20),
        status_provider=Mock(return_value=status(PlugState.ON, 20)),
        state_setter=setter,
        dry_run=False,
    )

    assert result.command_sent is False
    assert result.state_confirmed is True
    setter.assert_not_called()


def test_returns_structured_error_when_status_cannot_be_read():
    provider = Mock(
        side_effect=SwitchBotPlugError("PLUG_OFFLINE", "offline", True)
    )

    result = run_humidifier_control(
        ROOM,
        relative_humidity=40,
        current_time=time(20),
        status_provider=provider,
        state_setter=Mock(),
        dry_run=False,
    )

    assert result.error_code == "PLUG_OFFLINE"
    assert result.desired_state is None


def test_reports_unconfirmed_command():
    result = run_humidifier_control(
        ROOM,
        relative_humidity=40,
        current_time=time(20),
        status_provider=Mock(
            side_effect=[status(PlugState.OFF), status(PlugState.OFF)]
        ),
        state_setter=Mock(),
        dry_run=False,
    )

    assert result.error_code == "PLUG_STATE_NOT_CONFIRMED"
    assert result.state_confirmed is False


def test_rejects_room_without_humidifier():
    no_humidifier = RoomConfig("living", "sala", "meter", True)

    with pytest.raises(ValueError):
        run_humidifier_control(
            no_humidifier,
            40,
            time(20),
            Mock(),
            Mock(),
        )
