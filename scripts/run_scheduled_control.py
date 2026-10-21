"""Run one non-interactive environment-control cycle."""

from datetime import datetime
import json
import os
import uuid
from zoneinfo import ZoneInfo

from smart_home_qa_harness.application import (
    ConfigurationError,
    load_application_config,
    run_application,
)
from smart_home_qa_harness.notification_store import FileNotificationStore
from smart_home_qa_harness.operational_events import (
    build_operational_event,
    load_operational_alert_tracker,
)


def main(environ=None, now_factory=None) -> int:
    """Execute one control cycle and emit one versioned JSON event."""

    environ = os.environ if environ is None else environ
    now_factory = (
        (lambda: datetime.now(ZoneInfo("Europe/Berlin")))
        if now_factory is None
        else now_factory
    )
    current_datetime = now_factory()
    alert_tracker = load_operational_alert_tracker(environ)

    try:
        config = load_application_config(environ)
    except ConfigurationError as error:
        print(json.dumps(build_operational_event(
            timestamp=current_datetime,
            subsystem="ventilation",
            scope_kind="home",
            scope="home",
            decision="configuration_rejected",
            command_status="blocked",
            confirmation_status="not_applicable",
            error_code=error.code,
            alert_tracker=alert_tracker,
        ), sort_keys=True))
        return 1

    notification_store = FileNotificationStore(
        path=environ.get(
            "NOTIFICATION_STATE_FILE",
            ".state/notifications.json",
        )
    )
    result = run_application(
        config=config,
        current_datetime=current_datetime,
        nonce=str(uuid.uuid4()),
        reserve_notification=notification_store.reserve,
    )

    if result.webhook_sent:
        command_status = "succeeded"
    elif result.notification_suppressed:
        command_status = "suppressed"
    elif result.error_code is not None:
        command_status = "failed"
    else:
        command_status = "not_required"

    print(json.dumps(build_operational_event(
        timestamp=current_datetime,
        subsystem="ventilation",
        scope_kind="home",
        scope="home",
        decision=result.action.value,
        command_status=command_status,
        confirmation_status="not_supported",
        error_code=result.error_code,
        alert_tracker=alert_tracker,
        state={
            "notification_suppressed": result.notification_suppressed,
        },
    ), sort_keys=True))
    return 1 if result.error_code is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
