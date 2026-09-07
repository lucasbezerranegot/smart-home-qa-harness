import os
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import boto3

from smart_home_qa_harness.application import (
    ConfigurationError,
    load_application_config,
    run_application,
)
from smart_home_qa_harness.notification_store import (
    DynamoDBNotificationStore,
)


def build_notification_reserver(
    table_name: str,
    current_datetime: datetime,
) -> Callable[[str], bool]:
    """Build a DynamoDB reservation function with a fixed expiration."""

    table = boto3.resource("dynamodb").Table(
        table_name,
    )

    store = DynamoDBNotificationStore(
        table=table,
    )

    # DynamoDB TTL expects Unix time in seconds.
    expires_at = int(
        (
            current_datetime
            + timedelta(days=30)
        ).timestamp()
    )

    def reserve_notification(
        notification_key: str,
    ) -> bool:
        return store.reserve(
            notification_key=notification_key,
            expires_at=expires_at,
        )

    return reserve_notification


def lambda_handler(event, context) -> dict:
    """Execute one scheduled environment-control cycle."""

    config = load_application_config(os.environ)
    current_datetime = datetime.now(
        ZoneInfo("Europe/Berlin"),
    )

    try:
        table_name = os.environ["NOTIFICATION_TABLE_NAME"]
    except KeyError as error:
        raise ConfigurationError(
            code="MISSING_CONFIGURATION",
            message=(
                "Missing required configuration: "
                "NOTIFICATION_TABLE_NAME"
            ),
            retryable=False,
        ) from error

    reserve_notification = build_notification_reserver(
        table_name=table_name,
        current_datetime=current_datetime,
    )

    result = run_application(
        config=config,
        current_datetime=current_datetime,
        nonce=str(uuid.uuid4()),
        reserve_notification=reserve_notification,
    )

    status = (
        "error"
        if result.error_code is not None
        else "success"
    )

    return {
        "status": status,
        "action": result.action.value,
        "webhook_sent": result.webhook_sent,
        "notification_suppressed": result.notification_suppressed,
        "error_code": result.error_code,
    }
