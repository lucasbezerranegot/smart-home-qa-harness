"""Run one non-interactive environment-control cycle.

Unlike the manual smoke test, this script never forces a window action and
does not ask for confirmation. It is intended for scheduled automation.
"""

import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from smart_home_qa_harness.application import (
    ConfigurationError,
    load_application_config,
    run_application,
)


def main() -> int:
    """Execute one control cycle and return an operating-system exit code."""

    try:
        config = load_application_config(os.environ)
    except ConfigurationError as error:
        print(f"Configuration error: {error.code} - {error.message}")
        return 1

    current_datetime = datetime.now(
        ZoneInfo("Europe/Berlin"),
    )

    # This set only exists during the current GitHub Actions execution.
    # Persistent deduplication will be added later with DynamoDB.
    sent_notification_keys: set[str] = set()

    result = run_application(
        config=config,
        current_datetime=current_datetime,
        nonce=str(uuid.uuid4()),
        sent_notification_keys=sent_notification_keys,
    )

    print(f"Execution time: {current_datetime.isoformat()}")
    print(f"Decision: {result.action.value}")
    print(f"Webhook sent: {result.webhook_sent}")
    print(
        "Notification suppressed: "
        f"{result.notification_suppressed}"
    )

    if result.error_code is not None:
        print(f"Execution failed: {result.error_code}")
        return 1

    if result.webhook_sent:
        print("Alexa notification sent successfully.")
    else:
        print("Execution completed without sending a notification.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
