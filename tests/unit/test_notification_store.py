from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from smart_home_qa_harness.notification_store import (
    DynamoDBNotificationStore,
)


def test_reserve_notification_stores_new_key():
    # Arrange: this object behaves like a DynamoDB table, but no AWS call
    # can happen because it is only a mock.
    mock_table = MagicMock()

    store = DynamoDBNotificationStore(
        table=mock_table,
    )

    # Act: reserve one evening-notification period.
    result = store.reserve(
        notification_key="2026-09-06:evening",
        expires_at=1788800000,
    )

    # Assert: a successful DynamoDB reservation returns True.
    assert result is True

    # Assert: verify the exact contract sent to DynamoDB.
    mock_table.put_item.assert_called_once_with(
        Item={
            "notification_key": "2026-09-06:evening",
            "expires_at": 1788800000,
        },
        ConditionExpression=(
            "attribute_not_exists(notification_key)"
        ),
    )

def test_reserve_notification_returns_false_for_duplicate_key():
    # Arrange: DynamoDB uses this error when the condition
    # attribute_not_exists(notification_key) evaluates to false.
    duplicate_error = ClientError(
        error_response={
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "The conditional request failed",
            },
        },
        operation_name="PutItem",
    )

    mock_table = MagicMock()
    mock_table.put_item.side_effect = duplicate_error

    store = DynamoDBNotificationStore(
        table=mock_table,
    )

    # Act: an existing key is a normal deduplication result, not a crash.
    result = store.reserve(
        notification_key="2026-09-06:evening",
        expires_at=1788800000,
    )

    # Assert
    assert result is False

    mock_table.put_item.assert_called_once_with(
        Item={
            "notification_key": "2026-09-06:evening",
            "expires_at": 1788800000,
        },
        ConditionExpression=(
            "attribute_not_exists(notification_key)"
        ),
    )
def test_reserve_notification_reraises_unexpected_aws_error():
    # Arrange: lack of AWS permission is a technical failure.
    # It must not be interpreted as a duplicate notification.
    access_denied_error = ClientError(
        error_response={
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "Not authorized to access the table",
            },
        },
        operation_name="PutItem",
    )

    mock_table = MagicMock()
    mock_table.put_item.side_effect = access_denied_error

    store = DynamoDBNotificationStore(
        table=mock_table,
    )

    # Act and assert: confirm that the original AWS exception escapes.
    with pytest.raises(ClientError) as captured:
        store.reserve(
            notification_key="2026-09-06:evening",
            expires_at=1788800000,
        )

    assert captured.value is access_denied_error
    assert (
        captured.value.response["Error"]["Code"]
        == "AccessDeniedException"
    )

    mock_table.put_item.assert_called_once()
