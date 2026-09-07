import json

import pytest

from smart_home_qa_harness.notification_store import (
    FileNotificationStore,
    NotificationStoreError,
)


def test_reserve_persists_new_notification_key(tmp_path):
    state_file = tmp_path / "notifications.json"
    store = FileNotificationStore(state_file)

    result = store.reserve("2026-09-07:morning")

    assert result is True
    assert json.loads(state_file.read_text()) == [
        "2026-09-07:morning"
    ]


def test_reserve_returns_false_for_existing_key(tmp_path):
    state_file = tmp_path / "notifications.json"
    state_file.write_text('["2026-09-07:morning"]')
    store = FileNotificationStore(state_file)

    result = store.reserve("2026-09-07:morning")

    assert result is False
    assert json.loads(state_file.read_text()) == [
        "2026-09-07:morning"
    ]


def test_reserve_preserves_existing_keys(tmp_path):
    state_file = tmp_path / "notifications.json"
    state_file.write_text('["2026-09-06:evening"]')
    store = FileNotificationStore(state_file)

    store.reserve("2026-09-07:morning")

    assert json.loads(state_file.read_text()) == [
        "2026-09-06:evening",
        "2026-09-07:morning",
    ]


@pytest.mark.parametrize(
    "invalid_content",
    [
        "not-json",
        '{"notification_key": "2026-09-07:morning"}',
        '["valid-key", 123]',
    ],
)
def test_reserve_rejects_invalid_state_file(
    tmp_path,
    invalid_content,
):
    state_file = tmp_path / "notifications.json"
    state_file.write_text(invalid_content)
    store = FileNotificationStore(state_file)

    with pytest.raises(NotificationStoreError) as captured:
        store.reserve("2026-09-07:morning")

    assert captured.value.code == "INVALID_NOTIFICATION_STATE"
    assert captured.value.retryable is False
