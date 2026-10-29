"""Fail-safe delivery of actionable operational-event transitions."""

from collections.abc import Mapping
from typing import Any

from smart_home_qa_harness.ntfy_notifier import (
    NtfyNotificationError,
    NtfyNotifier,
)


def deliver_operational_notification(
    event: Mapping[str, Any],
    notifier: NtfyNotifier | None,
) -> dict[str, Any]:
    """Return the event with a redacted delivery result attached."""

    result = dict(event)
    alert = event.get("alert")
    notification_required = bool(
        isinstance(alert, Mapping)
        and alert.get("notification_required") is True
    )
    if not notification_required:
        result["notification_delivery"] = _delivery("not_required")
        return result
    if notifier is None:
        result["notification_delivery"] = _delivery("disabled")
        return result

    try:
        notifier.send(event)
    except NtfyNotificationError as error:
        result["notification_delivery"] = _delivery(
            "failed",
            error.code,
            error.retryable,
        )
    except Exception:
        result["notification_delivery"] = _delivery(
            "failed",
            "NTFY_DELIVERY_FAILED",
            False,
        )
    else:
        result["notification_delivery"] = _delivery("succeeded")
    return result


def _delivery(
    status: str,
    error_code: str | None = None,
    retryable: bool = False,
) -> dict[str, str | bool | None]:
    return {
        "provider": "ntfy",
        "status": status,
        "error_code": error_code,
        "retryable": retryable,
    }
