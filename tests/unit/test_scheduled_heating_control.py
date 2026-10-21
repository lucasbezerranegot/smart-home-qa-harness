import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.run_scheduled_heating_control import main
from smart_home_qa_harness.switchbot_relay_client import RelayState


def environment():
    return {
        "SWITCHBOT_TOKEN": "fake-token",
        "SWITCHBOT_SECRET": "fake-secret",
        "HEATING_MAXIMUM_READING_AGE_SECONDS": "600",
        "ALLOW_REAL_HEATING_COMMANDS": "true",
        "HEATING_SCHEDULED_ZONES": "children-room",
        "HEATING_ZONE_6_ENABLED": "true",
        "HEATING_ZONE_6_NAME": "children-room",
        "HEATING_ZONE_6_RELAY_ID": "relay-3",
        "HEATING_ZONE_6_CHANNEL": "2",
        "HEATING_ZONE_6_METER_ID": "children-room-meter",
        "HEATING_ZONE_6_TARGET_TEMPERATURE": "20",
        "HEATING_ZONE_6_HYSTERESIS": "0.5",
    }


def add_bedroom(environ, enabled="true"):
    environ.update(
        {
            "HEATING_ZONE_5_ENABLED": enabled,
            "HEATING_ZONE_5_NAME": "bedroom",
            "HEATING_ZONE_5_RELAY_ID": "relay-3",
            "HEATING_ZONE_5_CHANNEL": "1",
            "HEATING_ZONE_5_METER_ID": "bedroom-meter",
            "HEATING_ZONE_5_TARGET_TEMPERATURE": "20",
            "HEATING_ZONE_5_HYSTERESIS": "0.5",
        }
    )


def result(error_code=None):
    return SimpleNamespace(
        previous_state=RelayState.ON,
        desired_state=RelayState.OFF,
        command_sent=True,
        state_confirmed=error_code is None,
        error_code=error_code,
    )


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_runs_single_scheduled_zone_non_interactively(run_zone, capsys):
    run_zone.return_value = result()
    now = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)

    exit_code = main(environment(), now_factory=lambda: now)

    assert exit_code == 0
    run_zone.assert_called_once()
    assert run_zone.call_args.kwargs["dry_run"] is False
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    event = events[0]
    assert event["zone"] == "children-room"
    assert event["schema_version"] == 1
    assert event["subsystem"] == "heating"
    assert event["confirmation_status"] == "confirmed"
    assert event["command_status"] == "succeeded"
    assert "relay_id" not in event
    assert "meter_id" not in event
    assert events[1]["home"] == "home"
    assert events[1]["decision"] == "completed"


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_runs_multiple_scheduled_zones_in_allowlist_order(run_zone, capsys):
    environ = environment()
    add_bedroom(environ)
    environ["HEATING_SCHEDULED_ZONES"] = "children-room, bedroom"
    run_zone.side_effect = [result(), result()]

    exit_code = main(environ)

    assert exit_code == 0
    assert [call.kwargs["zone"].name for call in run_zone.call_args_list] == [
        "children-room",
        "bedroom",
    ]
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [event["zone"] for event in events[:-1]] == [
        "children-room",
        "bedroom",
    ]
    assert events[-1]["decision"] == "completed"


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_does_not_run_enabled_zone_omitted_from_allowlist(run_zone):
    environ = environment()
    add_bedroom(environ)
    run_zone.return_value = result()

    exit_code = main(environ)

    assert exit_code == 0
    run_zone.assert_called_once()
    assert run_zone.call_args.kwargs["zone"].name == "children-room"


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_blocks_scheduled_run_when_real_commands_are_not_allowed(
    run_zone, capsys
):
    environ = environment()
    environ["ALLOW_REAL_HEATING_COMMANDS"] = "false"

    exit_code = main(environ)

    assert exit_code == 1
    run_zone.assert_not_called()
    event = json.loads(capsys.readouterr().out)
    assert event["error_code"] == "REAL_HEATING_COMMANDS_NOT_ALLOWED"


@pytest.mark.parametrize(
    ("allowlist", "expected_code"),
    [
        (None, "MISSING_HEATING_SCHEDULE"),
        ("", "MISSING_HEATING_SCHEDULE"),
        ("children-room,", "INVALID_HEATING_SCHEDULE"),
        (
            "children-room,children-room",
            "DUPLICATE_SCHEDULED_HEATING_ZONE",
        ),
        ("unknown-room", "UNKNOWN_SCHEDULED_HEATING_ZONE"),
    ],
)
@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_invalid_allowlist_fails_closed(
    run_zone, allowlist, expected_code, capsys
):
    environ = environment()
    if allowlist is None:
        environ.pop("HEATING_SCHEDULED_ZONES")
    else:
        environ["HEATING_SCHEDULED_ZONES"] = allowlist

    exit_code = main(environ)

    assert exit_code == 1
    run_zone.assert_not_called()
    event = json.loads(capsys.readouterr().out)
    assert event["event"] == "operational_cycle"
    assert event["error_code"] == expected_code
    assert event["command_status"] == "blocked"


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_disabled_scheduled_zone_fails_closed(run_zone, capsys):
    environ = environment()
    add_bedroom(environ, enabled="false")
    environ["HEATING_SCHEDULED_ZONES"] = "bedroom"

    exit_code = main(environ)

    assert exit_code == 1
    run_zone.assert_not_called()
    event = json.loads(capsys.readouterr().out)
    assert event["error_code"] == "DISABLED_SCHEDULED_HEATING_ZONE"


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_incomplete_enabled_scheduled_zone_fails_closed(run_zone, capsys):
    environ = environment()
    add_bedroom(environ)
    environ["HEATING_SCHEDULED_ZONES"] = "bedroom"
    environ.pop("HEATING_ZONE_5_RELAY_ID")

    exit_code = main(environ)

    assert exit_code == 1
    run_zone.assert_not_called()
    event = json.loads(capsys.readouterr().out)
    assert event["error_code"] == "MISSING_HEATING_CONFIGURATION"


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_duplicate_relay_channel_fails_closed(run_zone, capsys):
    environ = environment()
    add_bedroom(environ)
    environ["HEATING_ZONE_5_CHANNEL"] = "2"
    environ["HEATING_SCHEDULED_ZONES"] = "bedroom,children-room"

    exit_code = main(environ)

    assert exit_code == 1
    run_zone.assert_not_called()
    event = json.loads(capsys.readouterr().out)
    assert event["error_code"] == "DUPLICATE_HEATING_RELAY_CHANNEL"


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_continues_after_zone_result_reports_error(run_zone, capsys):
    environ = environment()
    add_bedroom(environ)
    environ["HEATING_SCHEDULED_ZONES"] = "bedroom,children-room"
    run_zone.side_effect = [result("RELAY_UNAVAILABLE"), result()]

    exit_code = main(environ)

    assert exit_code == 1
    assert run_zone.call_count == 2
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[0]["error_code"] == "RELAY_UNAVAILABLE"
    assert events[1]["error_code"] is None
    assert events[2]["decision"] == "completed_with_errors"


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_continues_after_unexpected_zone_exception(run_zone, capsys):
    environ = environment()
    add_bedroom(environ)
    environ["HEATING_SCHEDULED_ZONES"] = "bedroom,children-room"
    run_zone.side_effect = [RuntimeError("provider failed"), result()]

    exit_code = main(environ)

    assert exit_code == 1
    assert run_zone.call_count == 2
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[0]["error_code"] == "HEATING_ZONE_EXECUTION_FAILED"
    assert events[0]["command_status"] == "unknown"
    assert events[1]["error_code"] is None
    assert events[2]["decision"] == "completed_with_errors"


@patch("scripts.run_scheduled_heating_control.run_switchbot_heating_zone")
def test_returns_failure_when_heating_cycle_is_not_confirmed(run_zone):
    run_zone.return_value = result("RELAY_STATE_NOT_CONFIRMED")

    exit_code = main(environment())

    assert exit_code == 1
