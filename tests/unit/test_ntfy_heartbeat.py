import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
import responses

from smart_home_qa_harness.ntfy_heartbeat import (
    HEARTBEAT_SEQUENCE_ID,
    NtfyHeartbeatError,
    load_ntfy_heartbeat_config,
    run_heartbeat,
)


NOW = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)
VALID_ENV = {
    "NTFY_ENABLED": "true",
    "NTFY_BASE_URL": "https://ntfy.sh",
    "NTFY_TOPIC": "private-home-alerts",
    "NTFY_ACCESS_TOKEN": "secret-access-token",
    "NTFY_HEARTBEAT_ENABLED": "true",
}


def _config(tmp_path: Path, **overrides):
    environ = VALID_ENV | {
        "NTFY_HEARTBEAT_STATE_FILE": str(tmp_path / "heartbeat.json"),
    } | overrides
    return load_ntfy_heartbeat_config(environ)


def _stored_state(config):
    return json.loads(config.state_file.read_text(encoding="utf-8"))


def test_loader_disables_heartbeat_by_default():
    assert load_ntfy_heartbeat_config({}) is None
    assert load_ntfy_heartbeat_config({
        "NTFY_HEARTBEAT_ENABLED": "false",
    }) is None


@pytest.mark.parametrize(
    "override",
    [
        {"NTFY_HEARTBEAT_ENABLED": "yes"},
        {"NTFY_ENABLED": "false"},
        {"NTFY_BASE_URL": "http://ntfy.sh"},
        {"NTFY_TOPIC": "secret topic"},
        {"NTFY_ACCESS_TOKEN": ""},
        {"NTFY_HEARTBEAT_DELAY_SECONDS": "nine hundred"},
        {"NTFY_HEARTBEAT_DELAY_SECONDS": "9"},
        {"NTFY_HEARTBEAT_DELAY_SECONDS": "259201"},
        {"NTFY_HEARTBEAT_STATE_FILE": ""},
        {"DASHBOARD_URL": "ftp://dashboard.local"},
        {"DASHBOARD_URL": "http://user:pass@dashboard.local"},
    ],
)
def test_invalid_configuration_is_redacted(override):
    with pytest.raises(NtfyHeartbeatError) as captured:
        load_ntfy_heartbeat_config(VALID_ENV | override)

    assert captured.value.code == "NTFY_HEARTBEAT_CONFIGURATION_INVALID"
    assert "secret-access-token" not in str(captured.value)
    assert "private-home-alerts" not in str(captured.value)


@responses.activate
def test_initial_renewal_schedules_one_failure_with_dashboard_link(tmp_path):
    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    config = _config(
        tmp_path,
        DASHBOARD_URL="http://smart-home.local/dashboard",
    )

    event = run_heartbeat(config, now=NOW)

    request = responses.calls[0].request
    payload = json.loads(request.body)
    assert request.headers["Authorization"] == "Bearer secret-access-token"
    assert payload == {
        "topic": "private-home-alerts",
        "sequence_id": HEARTBEAT_SEQUENCE_ID,
        "title": "Alerta: Raspberry Pi sem heartbeat",
        "message": (
            "O sistema da casa parou de renovar o heartbeat. "
            "As informações do dashboard podem estar desatualizadas."
        ),
        "priority": 5,
        "tags": ["warning", "house"],
        "delay": "900s",
        "click": "http://smart-home.local/dashboard",
    }
    assert event == {
        "event": "ntfy_heartbeat",
        "status": "renewed",
        "timestamp": NOW.isoformat(),
        "deadline": (NOW + timedelta(minutes=15)).isoformat(),
        "recovery_sent": False,
        "error_code": None,
    }
    assert _stored_state(config) == {
        "version": 1,
        "paused": False,
        "last_renewed_at": NOW.isoformat(),
        "deadline_at": (NOW + timedelta(minutes=15)).isoformat(),
        "pending_recovery_since": None,
    }


@responses.activate
def test_on_time_renewal_replaces_same_sequence_without_recovery(tmp_path):
    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    config = _config(tmp_path)
    run_heartbeat(config, now=NOW)

    event = run_heartbeat(config, now=NOW + timedelta(minutes=5))

    payloads = [json.loads(call.request.body) for call in responses.calls]
    assert [payload["sequence_id"] for payload in payloads] == [
        HEARTBEAT_SEQUENCE_ID,
        HEARTBEAT_SEQUENCE_ID,
    ]
    assert event["recovery_sent"] is False


@responses.activate
def test_renewal_at_deadline_sends_one_idempotent_recovery(tmp_path):
    for _ in range(3):
        responses.add(responses.POST, "https://ntfy.sh/", status=200)
    config = _config(
        tmp_path,
        DASHBOARD_URL="http://smart-home.local/dashboard",
    )
    run_heartbeat(config, now=NOW)

    event = run_heartbeat(config, now=NOW + timedelta(minutes=15))

    recovery = json.loads(responses.calls[2].request.body)
    assert event["recovery_sent"] is True
    assert recovery == {
        "topic": "private-home-alerts",
        "sequence_id": f"{HEARTBEAT_SEQUENCE_ID}-recovery-1794824100",
        "title": "Recuperação: heartbeat do Raspberry Pi",
        "message": (
            "O Raspberry Pi voltou a renovar o heartbeat.\n"
            "Indisponibilidade aproximada: 1min."
        ),
        "priority": 3,
        "tags": ["white_check_mark", "house"],
        "click": "http://smart-home.local/dashboard",
    }
    assert _stored_state(config)["pending_recovery_since"] is None

    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    next_event = run_heartbeat(
        config,
        now=NOW + timedelta(minutes=20),
    )
    assert next_event["recovery_sent"] is False


@responses.activate
def test_failed_recovery_is_retried_with_same_sequence_id(tmp_path):
    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    responses.add(responses.POST, "https://ntfy.sh/", status=503)
    config = _config(tmp_path)
    run_heartbeat(config, now=NOW)

    with pytest.raises(NtfyHeartbeatError):
        run_heartbeat(config, now=NOW + timedelta(minutes=16))

    assert _stored_state(config)["pending_recovery_since"] == (
        NOW + timedelta(minutes=15)
    ).isoformat()

    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    event = run_heartbeat(config, now=NOW + timedelta(minutes=20))
    failed_payload = json.loads(responses.calls[2].request.body)
    retried_payload = json.loads(responses.calls[4].request.body)
    assert event["recovery_sent"] is True
    assert retried_payload["sequence_id"] == failed_payload["sequence_id"]


@responses.activate
def test_failed_renewal_does_not_advance_persisted_deadline(tmp_path):
    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    responses.add(responses.POST, "https://ntfy.sh/", status=503)
    config = _config(tmp_path)
    run_heartbeat(config, now=NOW)

    with pytest.raises(NtfyHeartbeatError) as captured:
        run_heartbeat(config, now=NOW + timedelta(minutes=5))

    assert captured.value.code == "NTFY_HEARTBEAT_HTTP_ERROR"
    assert captured.value.retryable is True
    assert _stored_state(config)["deadline_at"] == (
        NOW + timedelta(minutes=15)
    ).isoformat()


@responses.activate
def test_pause_cancels_schedule_and_suppresses_automatic_renewals(tmp_path):
    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    responses.add(
        responses.DELETE,
        f"https://ntfy.sh/private-home-alerts/{HEARTBEAT_SEQUENCE_ID}",
        status=200,
    )
    config = _config(tmp_path)
    run_heartbeat(config, now=NOW)

    paused = run_heartbeat(config, "pause", NOW + timedelta(minutes=1))
    paused_again = run_heartbeat(
        config,
        "pause",
        NOW + timedelta(minutes=2),
    )
    still_paused = run_heartbeat(
        config,
        "renew",
        NOW + timedelta(minutes=5),
    )

    assert paused["status"] == "paused"
    assert paused_again["status"] == "paused"
    assert still_paused["status"] == "paused"
    assert len(responses.calls) == 2
    assert _stored_state(config)["paused"] is True


@responses.activate
def test_resume_schedules_without_false_recovery(tmp_path):
    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    responses.add(
        responses.DELETE,
        f"https://ntfy.sh/private-home-alerts/{HEARTBEAT_SEQUENCE_ID}",
        status=200,
    )
    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    config = _config(tmp_path)
    run_heartbeat(config, now=NOW)
    run_heartbeat(config, "pause", NOW + timedelta(minutes=1))

    resumed = run_heartbeat(
        config,
        "resume",
        NOW + timedelta(hours=1),
    )

    assert resumed["status"] == "renewed"
    assert resumed["recovery_sent"] is False
    assert _stored_state(config)["paused"] is False


def test_corrupt_state_fails_without_calling_ntfy(tmp_path):
    config = _config(tmp_path)
    config.state_file.write_text('{"token": "do-not-accept"}', encoding="utf-8")

    with patch(
        "smart_home_qa_harness.ntfy_heartbeat.requests.request"
    ) as request:
        with pytest.raises(NtfyHeartbeatError) as captured:
            run_heartbeat(config, now=NOW)

    assert captured.value.code == "NTFY_HEARTBEAT_STATE_ERROR"
    request.assert_not_called()


def test_invalid_action_is_rejected_before_publishing(tmp_path):
    config = _config(tmp_path)

    with patch(
        "smart_home_qa_harness.ntfy_heartbeat.requests.request"
    ) as request:
        with pytest.raises(NtfyHeartbeatError) as captured:
            run_heartbeat(config, "invalid", NOW)

    assert captured.value.code == "NTFY_HEARTBEAT_ACTION_INVALID"
    request.assert_not_called()


@pytest.mark.parametrize(
    "provider_error, expected_code",
    [
        (requests.exceptions.Timeout(), "NTFY_HEARTBEAT_TIMEOUT"),
        (
            requests.exceptions.ConnectionError(),
            "NTFY_HEARTBEAT_CONNECTION_ERROR",
        ),
    ],
)
def test_transport_failures_are_stable_and_redacted(
    tmp_path,
    provider_error,
    expected_code,
):
    config = _config(tmp_path)
    with patch(
        "smart_home_qa_harness.ntfy_heartbeat.requests.request",
        side_effect=provider_error,
    ):
        with pytest.raises(NtfyHeartbeatError) as captured:
            run_heartbeat(config, now=NOW)

    assert captured.value.code == expected_code
    assert captured.value.retryable is True
    assert "secret-access-token" not in str(captured.value)
