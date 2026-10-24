from unittest.mock import Mock

from smart_home_qa_harness.ntfy_notifier import NtfyNotificationError
from smart_home_qa_harness.operational_notifications import (
    deliver_operational_notification,
)


def _event(notification_required=True):
    return {
        "alert": {
            "status": "triggered",
            "notification_required": notification_required,
        }
    }


def test_ongoing_event_does_not_call_notifier():
    notifier = Mock()

    result = deliver_operational_notification(_event(False), notifier)

    notifier.send.assert_not_called()
    assert result["notification_delivery"] == {
        "provider": "ntfy",
        "status": "not_required",
        "error_code": None,
        "retryable": False,
    }


def test_required_event_reports_disabled_channel():
    result = deliver_operational_notification(_event(), None)

    assert result["notification_delivery"]["status"] == "disabled"


def test_successful_delivery_is_reported_without_configuration():
    notifier = Mock()

    result = deliver_operational_notification(_event(), notifier)

    notifier.send.assert_called_once()
    assert result["notification_delivery"] == {
        "provider": "ntfy",
        "status": "succeeded",
        "error_code": None,
        "retryable": False,
    }
    assert "topic" not in result["notification_delivery"]
    assert "token" not in result["notification_delivery"]


def test_known_failure_keeps_stable_code_and_retryability():
    notifier = Mock()
    notifier.send.side_effect = NtfyNotificationError(
        "NTFY_TIMEOUT",
        True,
    )

    result = deliver_operational_notification(_event(), notifier)

    assert result["notification_delivery"] == {
        "provider": "ntfy",
        "status": "failed",
        "error_code": "NTFY_TIMEOUT",
        "retryable": True,
    }


def test_unexpected_failure_is_contained():
    notifier = Mock()
    notifier.send.side_effect = RuntimeError("sensitive provider details")

    result = deliver_operational_notification(_event(), notifier)

    assert result["notification_delivery"] == {
        "provider": "ntfy",
        "status": "failed",
        "error_code": "NTFY_DELIVERY_FAILED",
        "retryable": False,
    }
