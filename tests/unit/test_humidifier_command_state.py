import json
from datetime import datetime, time, timedelta, timezone
from unittest.mock import Mock

from smart_home_qa_harness.humidifier_command_state import (
    FileHumidifierCommandStore,
)
from smart_home_qa_harness.humidifier_control import run_humidifier_control
from smart_home_qa_harness.humidifier_provider import (
    HumidifierProviderError,
    HumidifierProviderStatus,
    HumidifierState,
)
from smart_home_qa_harness.room_config import (
    HumidifierProviderKind,
    RoomConfig,
)


NOW = datetime(2026, 10, 30, 20, 0, tzinfo=timezone.utc)
ROOM = RoomConfig(
    "bedroom",
    "quarto",
    "meter-bedroom",
    True,
    HumidifierProviderKind.VESYNC,
    "secret-cid",
)


def _provider(*states):
    target = Mock(provider_name="vesync", device_id="secret-cid")
    target.read_status.side_effect = [
        HumidifierProviderStatus(
            "vesync", "secret-cid", state, True, True
        )
        for state in states
    ]
    return target


def _run(target, store, now=NOW):
    return run_humidifier_control(
        room=ROOM,
        relative_humidity=40,
        current_time=time(20),
        provider=target,
        dry_run=False,
        pending_command_store=store,
        current_datetime=now,
        confirmation_deadline_seconds=600,
    )


def test_accepted_command_is_reserved_and_not_immediately_polled(tmp_path):
    store = FileHumidifierCommandStore(tmp_path / "commands.json")
    target = _provider(HumidifierState.OFF)

    result = _run(target, store)

    target.set_state.assert_called_once_with(HumidifierState.ON)
    assert target.read_status.call_count == 1
    assert result.confirmation_pending is True
    assert result.error_code is None
    pending = store.get("bedroom")
    assert pending is not None
    assert pending.desired_state is HumidifierState.ON
    serialized = (tmp_path / "commands.json").read_text()
    assert "secret-cid" not in serialized


def test_later_cycle_confirms_and_clears_without_resending(tmp_path):
    store = FileHumidifierCommandStore(tmp_path / "commands.json")
    first = _provider(HumidifierState.OFF)
    _run(first, store)
    later = _provider(HumidifierState.ON)

    result = _run(later, store, NOW + timedelta(minutes=5))

    later.set_state.assert_not_called()
    assert result.state_confirmed is True
    assert result.confirmation_pending is False
    assert result.error_code is None
    assert store.get("bedroom") is None


def test_stale_state_is_pending_then_stable_failure_without_resend(tmp_path):
    store = FileHumidifierCommandStore(tmp_path / "commands.json")
    _run(_provider(HumidifierState.OFF), store)

    pending = _run(
        _provider(HumidifierState.OFF),
        store,
        NOW + timedelta(minutes=5),
    )
    expired_target = _provider(HumidifierState.OFF)
    expired = _run(
        expired_target,
        store,
        NOW + timedelta(minutes=10),
    )

    assert pending.confirmation_pending is True
    assert pending.error_code is None
    assert expired.confirmation_pending is False
    assert expired.error_code == "HUMIDIFIER_STATE_NOT_CONFIRMED"
    expired_target.set_state.assert_not_called()


def test_temporary_offline_is_deferred_while_command_is_pending(tmp_path):
    store = FileHumidifierCommandStore(tmp_path / "commands.json")
    _run(_provider(HumidifierState.OFF), store)
    offline = _provider()
    offline.read_status.side_effect = HumidifierProviderError(
        "VESYNC_HUMIDIFIER_OFFLINE", "offline", True
    )

    result = _run(offline, store, NOW + timedelta(minutes=5))

    assert result.confirmation_pending is True
    assert result.error_code is None
    offline.set_state.assert_not_called()


def test_corrupt_state_fails_closed_before_device_access(tmp_path):
    state_path = tmp_path / "commands.json"
    state_path.write_text(json.dumps({"schema_version": 99, "entries": {}}))
    store = FileHumidifierCommandStore(state_path)
    target = _provider(HumidifierState.OFF)

    result = _run(target, store)

    assert result.error_code == "INVALID_HUMIDIFIER_COMMAND_STATE"
    target.read_status.assert_not_called()
    target.set_state.assert_not_called()


def test_definitively_rejected_command_does_not_remain_pending(tmp_path):
    store = FileHumidifierCommandStore(tmp_path / "commands.json")
    target = _provider(HumidifierState.OFF)
    target.set_state.side_effect = HumidifierProviderError(
        "VESYNC_COMMAND_REJECTED", "rejected", True
    )

    result = _run(target, store)

    assert result.error_code == "VESYNC_COMMAND_REJECTED"
    assert store.get("bedroom") is None


def test_switchbot_plug_keeps_immediate_confirmation_path(tmp_path):
    room = RoomConfig(
        "living-room-kitchen",
        "sala de jantar",
        "meter-living",
        True,
        HumidifierProviderKind.SWITCHBOT_PLUG,
        "plug-living",
    )
    target = Mock(
        provider_name="switchbot-plug", device_id="plug-living"
    )
    target.read_status.side_effect = [
        HumidifierProviderStatus(
            "switchbot-plug",
            "plug-living",
            HumidifierState.OFF,
            True,
        ),
        HumidifierProviderStatus(
            "switchbot-plug",
            "plug-living",
            HumidifierState.ON,
            True,
        ),
    ]
    store = FileHumidifierCommandStore(tmp_path / "commands.json")

    result = run_humidifier_control(
        room=room,
        relative_humidity=40,
        current_time=time(20),
        provider=target,
        dry_run=False,
        pending_command_store=store,
        current_datetime=NOW,
    )

    target.set_state.assert_called_once_with(HumidifierState.ON)
    assert target.read_status.call_count == 2
    assert result.state_confirmed is True
    assert result.confirmation_pending is False
    assert not (tmp_path / "commands.json").exists()


def test_dry_run_never_clears_persisted_pending_state(tmp_path):
    store = FileHumidifierCommandStore(tmp_path / "commands.json")
    _run(_provider(HumidifierState.OFF), store)
    target = _provider(HumidifierState.ON)

    result = run_humidifier_control(
        room=ROOM,
        relative_humidity=40,
        current_time=time(20),
        provider=target,
        dry_run=True,
        pending_command_store=store,
        current_datetime=NOW + timedelta(minutes=5),
    )

    assert result.state_confirmed is True
    assert store.get("bedroom") is not None
    target.set_state.assert_not_called()
