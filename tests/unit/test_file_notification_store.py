import json
from concurrent.futures import ProcessPoolExecutor

import pytest

from smart_home_qa_harness.notification_store import (
    FileNotificationStore,
    NotificationStoreError,
)


def _reserve_shared_notification(path):
    return FileNotificationStore(path).reserve("2026-10-24:morning")


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
    assert state_file.read_text() == invalid_content


def test_concurrent_reservations_have_exactly_one_winner(tmp_path):
    state_file = tmp_path / "notifications.json"

    with ProcessPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(
            _reserve_shared_notification,
            [state_file] * 24,
        ))

    assert results.count(True) == 1
    assert results.count(False) == 23
    assert json.loads(state_file.read_text()) == [
        "2026-10-24:morning"
    ]


def test_reserve_removes_expired_dated_keys_and_preserves_legacy_keys(
    tmp_path,
):
    state_file = tmp_path / "notifications.json"
    state_file.write_text(json.dumps([
        "legacy-reservation",
        "2026-07-25:morning",
        "2026-07-26:evening",
    ]))
    store = FileNotificationStore(state_file, retention_days=90)

    store.reserve("2026-10-24:morning")

    assert json.loads(state_file.read_text()) == [
        "2026-07-26:evening",
        "2026-10-24:morning",
        "legacy-reservation",
    ]


def test_reserve_ignores_orphaned_temporary_file(tmp_path):
    state_file = tmp_path / "notifications.json"
    orphan = tmp_path / ".notifications.json.interrupted.tmp"
    orphan.write_text("partial")

    result = FileNotificationStore(state_file).reserve(
        "2026-10-24:evening"
    )

    assert result is True
    assert json.loads(state_file.read_text()) == [
        "2026-10-24:evening"
    ]
    assert orphan.read_text() == "partial"


@pytest.mark.parametrize("retention_days", [0, -1, True, 1.5, "90"])
def test_store_rejects_invalid_retention(tmp_path, retention_days):
    with pytest.raises(ValueError):
        FileNotificationStore(
            tmp_path / "notifications.json",
            retention_days=retention_days,
        )
