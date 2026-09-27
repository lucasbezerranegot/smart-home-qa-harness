from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from scripts.run_scheduled_heating_control import main
from smart_home_qa_harness.switchbot_relay_client import RelayState


def environment():
    return {
        "SWITCHBOT_TOKEN": "fake-token",
        "SWITCHBOT_SECRET": "fake-secret",
        "HEATING_MAXIMUM_READING_AGE_SECONDS": "600",
        "ALLOW_REAL_HEATING_COMMANDS": "true",
        "HEATING_SCHEDULED_ZONE": "children-room",
        "HEATING_ZONE_6_ENABLED": "true",
        "HEATING_ZONE_6_NAME": "children-room",
        "HEATING_ZONE_6_RELAY_ID": "relay-3",
        "HEATING_ZONE_6_CHANNEL": "2",
        "HEATING_ZONE_6_METER_ID": "children-room-meter",
        "HEATING_ZONE_6_TARGET_TEMPERATURE": "20",
        "HEATING_ZONE_6_HYSTERESIS": "0.5",
    }


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_runs_single_children_room_zone_non_interactively(run_zone, capsys):
    run_zone.return_value = SimpleNamespace(
        relay_id="relay-3",
        channel=2,
        meter_id="children-room-meter",
        previous_state=RelayState.ON,
        desired_state=RelayState.OFF,
        command_sent=True,
        state_confirmed=True,
        error_code=None,
    )
    now = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)

    exit_code = main(environment(), now_factory=lambda: now)

    assert exit_code == 0
    run_zone.assert_called_once()
    assert run_zone.call_args.kwargs["dry_run"] is False
    output = capsys.readouterr().out
    assert '"zone": "children-room"' in output
    assert '"state_confirmed": true' in output


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_blocks_scheduled_run_when_real_commands_are_not_allowed(run_zone):
    environ = environment()
    environ["ALLOW_REAL_HEATING_COMMANDS"] = "false"

    exit_code = main(environ)

    assert exit_code == 1
    run_zone.assert_not_called()


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_blocks_scheduled_run_when_another_zone_is_enabled(run_zone):
    environ = environment()
    environ.update(
        {
            "HEATING_ZONE_5_ENABLED": "true",
            "HEATING_ZONE_5_NAME": "bedroom",
            "HEATING_ZONE_5_RELAY_ID": "relay-3",
            "HEATING_ZONE_5_CHANNEL": "1",
            "HEATING_ZONE_5_METER_ID": "bedroom-meter",
            "HEATING_ZONE_5_TARGET_TEMPERATURE": "20",
            "HEATING_ZONE_5_HYSTERESIS": "0.5",
        }
    )

    exit_code = main(environ)

    assert exit_code == 1
    run_zone.assert_not_called()


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_returns_failure_when_heating_cycle_reports_error(run_zone):
    run_zone.return_value = SimpleNamespace(
        relay_id="relay-3",
        channel=2,
        meter_id="children-room-meter",
        previous_state=RelayState.ON,
        desired_state=RelayState.OFF,
        command_sent=True,
        state_confirmed=False,
        error_code="RELAY_STATE_NOT_CONFIRMED",
    )

    exit_code = main(environment())

    assert exit_code == 1
