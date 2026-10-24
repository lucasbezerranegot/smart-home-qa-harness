import json
from unittest.mock import patch

import pytest
import requests
import responses

from smart_home_qa_harness.ntfy_notifier import (
    NTFY_TIMEOUT_SECONDS,
    NtfyNotificationError,
    load_ntfy_notifier,
)


VALID_ENV = {
    "NTFY_ENABLED": "true",
    "NTFY_BASE_URL": "https://ntfy.sh",
    "NTFY_TOPIC": "private-home-alerts",
    "NTFY_ACCESS_TOKEN": "secret-access-token",
}


def _event(status="triggered", error_code="RELAY_OFFLINE"):
    return {
        "schema_version": 1,
        "event": "operational_cycle",
        "timestamp": "2026-10-25T08:00:00+01:00",
        "subsystem": "heating",
        "zone": "kitchen",
        "error_code": error_code,
        "alert": {
            "status": status,
            "consecutive_failures": 3 if error_code else 0,
            "notification_required": True,
        },
    }


def test_loader_disables_ntfy_by_default():
    assert load_ntfy_notifier({}) is None
    assert load_ntfy_notifier({"NTFY_ENABLED": "false"}) is None


@pytest.mark.parametrize(
    "override",
    [
        {"NTFY_ENABLED": "yes"},
        {"NTFY_BASE_URL": "http://ntfy.sh"},
        {"NTFY_BASE_URL": "https://user:pass@ntfy.sh"},
        {"NTFY_BASE_URL": "https://ntfy.sh/path"},
        {"NTFY_TOPIC": "invalid topic"},
        {"NTFY_TOPIC": ""},
        {"NTFY_ACCESS_TOKEN": ""},
    ],
)
def test_invalid_configuration_fails_without_exposing_values(override):
    environ = VALID_ENV | override
    notifier = load_ntfy_notifier(environ)

    with pytest.raises(NtfyNotificationError) as captured:
        notifier.send(_event())

    assert captured.value.code == "NTFY_CONFIGURATION_INVALID"
    assert captured.value.retryable is False
    assert "secret-access-token" not in str(captured.value)
    assert "private-home-alerts" not in str(captured.value)


@responses.activate
def test_failure_notification_uses_authenticated_json_api():
    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    notifier = load_ntfy_notifier(VALID_ENV)

    notifier.send(_event())

    request = responses.calls[0].request
    assert request.headers["Authorization"] == "Bearer secret-access-token"
    assert json.loads(request.body) == {
        "topic": "private-home-alerts",
        "title": "Falha: Aquecimento — kitchen",
        "message": (
            "Código: RELAY_OFFLINE\n"
            "Falhas consecutivas: 3\n"
            "Horário: 2026-10-25T08:00:00+01:00"
        ),
        "priority": 4,
        "tags": ["warning", "house"],
    }


@responses.activate
def test_recovery_notification_uses_normal_priority():
    responses.add(responses.POST, "https://ntfy.sh/", status=200)
    notifier = load_ntfy_notifier(VALID_ENV)

    notifier.send(_event("recovered", None))

    payload = json.loads(responses.calls[0].request.body)
    assert payload == {
        "topic": "private-home-alerts",
        "title": "Recuperação: Aquecimento — kitchen",
        "message": (
            "O subsistema voltou a operar normalmente.\n"
            "Horário: 2026-10-25T08:00:00+01:00"
        ),
        "priority": 3,
        "tags": ["white_check_mark", "house"],
    }


@pytest.mark.parametrize(
    "status_code, retryable",
    [(401, False), (429, True), (503, True)],
)
@responses.activate
def test_http_failures_have_one_redacted_code(status_code, retryable):
    responses.add(
        responses.POST,
        "https://ntfy.sh/",
        status=status_code,
        body="provider body containing details",
    )
    notifier = load_ntfy_notifier(VALID_ENV)

    with pytest.raises(NtfyNotificationError) as captured:
        notifier.send(_event())

    assert captured.value.code == "NTFY_HTTP_ERROR"
    assert captured.value.retryable is retryable
    assert "provider body" not in str(captured.value)


@pytest.mark.parametrize(
    "provider_error, expected_code",
    [
        (requests.exceptions.Timeout(), "NTFY_TIMEOUT"),
        (requests.exceptions.ConnectionError(), "NTFY_CONNECTION_ERROR"),
    ],
)
def test_transport_failures_are_retryable(provider_error, expected_code):
    notifier = load_ntfy_notifier(VALID_ENV)

    with patch(
        "smart_home_qa_harness.ntfy_notifier.requests.post",
        side_effect=provider_error,
    ) as post:
        with pytest.raises(NtfyNotificationError) as captured:
            notifier.send(_event())

    assert captured.value.code == expected_code
    assert captured.value.retryable is True
    assert post.call_args.kwargs["timeout"] == NTFY_TIMEOUT_SECONDS
