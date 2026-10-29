import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import responses

from smart_home_qa_harness.application import ConfigurationError
from scripts.run_room_control import main as room_main
from scripts.run_scheduled_control import main as ventilation_main
from smart_home_qa_harness.decision_engine import WindowAction
from smart_home_qa_harness.orchestrator import OrchestrationResult


NOW = datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc)


@patch("scripts.run_scheduled_control.run_application")
@patch("scripts.run_scheduled_control.load_application_config")
def test_legacy_ventilation_runner_emits_one_structured_event(
    load_config,
    run_application,
    capsys,
    tmp_path,
):
    load_config.return_value = object()
    run_application.return_value = OrchestrationResult(
        action=WindowAction.OPEN_WINDOWS,
        webhook_sent=True,
    )
    environ = {
        "NOTIFICATION_STATE_FILE": str(tmp_path / "notifications.json"),
        "OPERATIONAL_ALERT_STATE_FILE": str(tmp_path / "alerts.json"),
    }

    exit_code = ventilation_main(environ, now_factory=lambda: NOW)

    assert exit_code == 0
    event = json.loads(capsys.readouterr().out)
    assert event["schema_version"] == 1
    assert event["subsystem"] == "ventilation"
    assert event["home"] == "home"
    assert event["decision"] == "OPEN_WINDOWS"
    assert event["command_status"] == "succeeded"
    assert event["error_code"] is None


@patch("scripts.run_room_control.run_room_control_cycle")
@patch("scripts.run_room_control.load_room_control_config")
def test_room_runner_emits_redacted_events_for_each_subsystem(
    load_config,
    run_cycle,
    capsys,
):
    load_config.return_value = SimpleNamespace(
        home=SimpleNamespace(
            rooms=(
                SimpleNamespace(room_id="children-room"),
                SimpleNamespace(room_id="bedroom"),
            )
        )
    )
    room = SimpleNamespace(room_id="bedroom")
    run_cycle.return_value = SimpleNamespace(
        reading_failures=(
            SimpleNamespace(
                room_id="children-room",
                error_code="METER_TIMEOUT",
            ),
        ),
        weather_error_code=None,
        ventilation=SimpleNamespace(
            decisions=(
                SimpleNamespace(
                    room=room,
                    action=SimpleNamespace(value="NO_ACTION"),
                    reason=SimpleNamespace(value="NO_RULE_MATCHED"),
                    temperature=20.0,
                    relative_humidity=53.0,
                ),
            ),
            failures=(),
        ),
        humidifiers=(
            SimpleNamespace(
                room_id="bedroom",
                provider_name="provider-name",
                device_id="sensitive-device-id",
                desired_state=SimpleNamespace(value="ON"),
                previous_state=SimpleNamespace(value="OFF"),
                reported_state=SimpleNamespace(value="ON"),
                relative_humidity=53.0,
                command_attempted=True,
                command_succeeded=True,
                dry_run=False,
                state_confirmed=True,
                error_code=None,
            ),
        ),
    )

    exit_code = room_main({}, now_factory=lambda: NOW)

    assert exit_code == 1
    output = capsys.readouterr().out
    events = [json.loads(line) for line in output.splitlines()]
    assert [event["subsystem"] for event in events] == [
        "environment_reading",
        "environment_reading",
        "weather",
        "ventilation",
        "humidifier",
        "room_control",
    ]
    assert all(event["schema_version"] == 1 for event in events)
    assert events[-2]["command_status"] == "succeeded"
    assert events[-1]["decision"] == "completed_with_errors"
    assert "sensitive-device-id" not in output
    assert "device_id" not in output
    assert "provider-name" not in output


@patch("scripts.run_room_control.load_room_control_config")
def test_room_configuration_failure_uses_stable_common_schema(
    load_config,
    capsys,
):
    from smart_home_qa_harness.room_control_application import (
        RoomControlApplicationError,
    )

    load_config.side_effect = RoomControlApplicationError(
        "MISSING_ROOM_CONTROL_CONFIGURATION",
        "message containing no secret",
    )

    exit_code = room_main({}, now_factory=lambda: NOW)

    assert exit_code == 1
    event = json.loads(capsys.readouterr().out)
    assert event["decision"] == "configuration_rejected"
    assert event["command_status"] == "blocked"
    assert event["error_code"] == "MISSING_ROOM_CONTROL_CONFIGURATION"


@responses.activate
@patch("scripts.run_scheduled_control.load_application_config")
def test_runner_delivers_threshold_alert_through_ntfy(
    load_config,
    capsys,
    tmp_path,
):
    load_config.side_effect = ConfigurationError(
        "MISSING_CONFIGURATION",
        "safe message",
        False,
    )
    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    environ = {
        "OPERATIONAL_ALERT_STATE_FILE": str(tmp_path / "alerts.json"),
        "OPERATIONAL_ALERT_AFTER_CONSECUTIVE_FAILURES": "1",
        "NTFY_ENABLED": "true",
        "NTFY_BASE_URL": "https://ntfy.sh",
        "NTFY_TOPIC": "private-home-alerts",
        "NTFY_ACCESS_TOKEN": "secret-access-token",
    }

    exit_code = ventilation_main(environ, now_factory=lambda: NOW)

    assert exit_code == 1
    event = json.loads(capsys.readouterr().out)
    assert event["notification_delivery"] == {
        "provider": "ntfy",
        "status": "succeeded",
        "error_code": None,
        "retryable": False,
    }
    assert len(responses.calls) == 1
    assert "private-home-alerts" not in json.dumps(event)
    assert "secret-access-token" not in json.dumps(event)
