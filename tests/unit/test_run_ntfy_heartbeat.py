from datetime import datetime, timezone
import json
from unittest.mock import patch

from scripts.run_ntfy_heartbeat import main
from smart_home_qa_harness.ntfy_heartbeat import NtfyHeartbeatError


NOW = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)


def test_disabled_runner_is_a_success(capsys):
    assert main([], environ={}, now_factory=lambda: NOW) == 0

    event = json.loads(capsys.readouterr().out)
    assert event["status"] == "disabled"
    assert event["error_code"] is None


@patch("scripts.run_ntfy_heartbeat.run_heartbeat")
@patch("scripts.run_ntfy_heartbeat.load_ntfy_heartbeat_config")
def test_runner_forwards_selected_action(loader, run, capsys):
    config = object()
    loader.return_value = config
    run.return_value = {
        "event": "ntfy_heartbeat",
        "status": "paused",
        "timestamp": NOW.isoformat(),
    }

    assert main(["pause"], {}, lambda: NOW) == 0

    run.assert_called_once_with(config, "pause", NOW)
    assert json.loads(capsys.readouterr().out)["status"] == "paused"


@patch("scripts.run_ntfy_heartbeat.load_ntfy_heartbeat_config")
def test_runner_logs_only_stable_failure_fields(loader, capsys):
    loader.side_effect = NtfyHeartbeatError(
        "NTFY_HEARTBEAT_CONNECTION_ERROR",
        True,
    )

    assert main([], environ={}, now_factory=lambda: NOW) == 1

    output = capsys.readouterr().out
    event = json.loads(output)
    assert event["status"] == "failed"
    assert event["error_code"] == "NTFY_HEARTBEAT_CONNECTION_ERROR"
    assert event["retryable"] is True
    assert "token" not in output
    assert "topic" not in output
