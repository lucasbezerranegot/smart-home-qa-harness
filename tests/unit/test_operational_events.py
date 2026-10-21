import json
from datetime import datetime, timezone

import pytest

from smart_home_qa_harness.operational_events import (
    FileOperationalAlertTracker,
    build_operational_event,
    load_operational_alert_tracker,
)


def test_event_has_versioned_common_schema_and_no_device_identifiers():
    event = build_operational_event(
        timestamp=datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc),
        subsystem="heating",
        scope_kind="zone",
        scope="bedroom",
        decision="ON",
        command_status="succeeded",
        confirmation_status="confirmed",
        error_code=None,
        measurements={"temperature_celsius": 19.5},
        state={"previous": "OFF"},
    )

    assert event["schema_version"] == 1
    assert event["event"] == "operational_cycle"
    assert event["zone"] == "bedroom"
    assert event["alert"]["status"] == "untracked"
    serialized = json.dumps(event)
    assert "device_id" not in serialized
    assert "token" not in serialized
    assert "secret" not in serialized


def test_tracker_alerts_once_then_reports_one_recovery(tmp_path):
    tracker = FileOperationalAlertTracker(
        tmp_path / "operational-alerts.json",
        alert_after=3,
    )

    first = tracker.evaluate("humidifier", "bedroom", "PROVIDER_TIMEOUT")
    second = tracker.evaluate("humidifier", "bedroom", "PROVIDER_TIMEOUT")
    third = tracker.evaluate("humidifier", "bedroom", "PROVIDER_TIMEOUT")
    fourth = tracker.evaluate("humidifier", "bedroom", "PROVIDER_TIMEOUT")
    recovery = tracker.evaluate("humidifier", "bedroom", None)
    healthy = tracker.evaluate("humidifier", "bedroom", None)

    assert (first.status, first.consecutive_failures) == ("pending", 1)
    assert (second.status, second.consecutive_failures) == ("pending", 2)
    assert third.status == "triggered"
    assert third.notification_required is True
    assert fourth.status == "ongoing"
    assert fourth.notification_required is False
    assert recovery.status == "recovered"
    assert recovery.notification_required is True
    assert healthy.status == "healthy"
    assert healthy.notification_required is False


def test_different_error_restarts_consecutive_failure_count(tmp_path):
    tracker = FileOperationalAlertTracker(tmp_path / "alerts.json", 2)
    tracker.evaluate("heating", "bedroom", "FIRST_ERROR")

    result = tracker.evaluate("heating", "bedroom", "SECOND_ERROR")

    assert result.status == "pending"
    assert result.consecutive_failures == 1


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        '{"schema_version": 2, "entries": {}}',
        '{"schema_version": 1, "entries": {"bad": {}}}',
    ],
)
def test_invalid_state_is_reported_without_breaking_event_creation(
    tmp_path,
    content,
):
    path = tmp_path / "alerts.json"
    path.write_text(content)
    tracker = FileOperationalAlertTracker(path)

    event = build_operational_event(
        timestamp=datetime.now(timezone.utc),
        subsystem="heating",
        scope_kind="zone",
        scope="bedroom",
        decision="OFF",
        command_status="not_required",
        confirmation_status="confirmed",
        error_code=None,
        alert_tracker=tracker,
    )

    assert event["alert"]["status"] == "unavailable"
    assert event["observability_error_code"] in {
        "INVALID_OPERATIONAL_ALERT_STATE",
        "OPERATIONAL_ALERT_STATE_UNAVAILABLE",
    }


def test_load_tracker_is_optional_and_validates_threshold(tmp_path):
    assert load_operational_alert_tracker({}) is None
    assert load_operational_alert_tracker({
        "OPERATIONAL_ALERT_STATE_FILE": str(tmp_path / "alerts.json"),
        "OPERATIONAL_ALERT_AFTER_CONSECUTIVE_FAILURES": "invalid",
    }) is None

    tracker = load_operational_alert_tracker({
        "OPERATIONAL_ALERT_STATE_FILE": str(tmp_path / "alerts.json"),
        "OPERATIONAL_ALERT_AFTER_CONSECUTIVE_FAILURES": "4",
    })

    assert tracker is not None
    assert tracker.alert_after == 4


@pytest.mark.parametrize("scope_kind", ["device", "building", ""])
def test_event_rejects_unknown_scope_kind(scope_kind):
    with pytest.raises(ValueError):
        build_operational_event(
            timestamp=datetime.now(timezone.utc),
            subsystem="heating",
            scope_kind=scope_kind,
            scope="bedroom",
            decision="OFF",
            command_status="not_required",
            confirmation_status="confirmed",
            error_code=None,
        )


@pytest.mark.parametrize("threshold", [0, -1, True, 1.5, "3"])
def test_tracker_rejects_invalid_threshold(tmp_path, threshold):
    with pytest.raises(ValueError):
        FileOperationalAlertTracker(tmp_path / "alerts.json", threshold)
