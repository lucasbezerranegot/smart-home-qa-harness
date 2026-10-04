from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp import ClientConnectionError
import pytest
from pyvesync.const import ConnectionStatus, DeviceStatus

from smart_home_qa_harness.humidifier_provider import (
    HumidifierProviderError,
    HumidifierState,
)
from smart_home_qa_harness.humidifier_control import run_humidifier_control
from smart_home_qa_harness.room_config import (
    HumidifierProviderKind,
    RoomConfig,
)
from smart_home_qa_harness.vesync_humidifier_provider import (
    VeSyncHumidifierProvider,
)


class FakeManager:
    def __init__(self, humidifiers=(), logged_in=True):
        self.enabled = logged_in
        self.login = AsyncMock(return_value=logged_in)
        self.get_devices = AsyncMock(return_value=True)
        self.devices = SimpleNamespace(humidifiers=list(humidifiers))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exception_type, exception, traceback):
        return False


def fake_device(
    state=DeviceStatus.OFF,
    connection=ConnectionStatus.ONLINE,
    cid="levoit-children",
):
    return SimpleNamespace(
        cid=cid,
        state=SimpleNamespace(
            device_status=state,
            connection_status=connection,
        ),
        update=AsyncMock(),
        turn_on=AsyncMock(return_value=True),
        turn_off=AsyncMock(return_value=True),
    )


def provider(manager):
    return VeSyncHumidifierProvider(
        username="parent@example.com",
        password="secret",
        humidifier_device_id="levoit-children",
        country_code="DE",
        time_zone="Europe/Berlin",
        timeout_seconds=15,
        manager_factory=Mock(return_value=manager),
    )


@pytest.mark.parametrize(
    "vesync_state,common_state",
    [
        (DeviceStatus.ON, HumidifierState.ON),
        (DeviceStatus.RUNNING, HumidifierState.ON),
        (DeviceStatus.OFF, HumidifierState.OFF),
        (DeviceStatus.STANDBY, HumidifierState.OFF),
    ],
)
def test_reads_and_normalizes_confirmed_humidifier_state(
    vesync_state,
    common_state,
):
    device = fake_device(state=vesync_state)

    result = provider(FakeManager([device])).read_status()

    assert result.provider_name == "vesync"
    assert result.device_id == "levoit-children"
    assert result.reported_state is common_state
    assert result.state_confirmed is True
    device.update.assert_awaited_once_with()


def test_resolves_only_humidifier_with_exact_configured_cid():
    another = fake_device(cid="another-device")

    with pytest.raises(HumidifierProviderError) as captured:
        provider(FakeManager([another])).read_status()

    assert captured.value.code == "VESYNC_HUMIDIFIER_NOT_FOUND"
    another.update.assert_not_awaited()


def test_rejects_offline_device_without_reporting_false_state():
    device = fake_device(connection=ConnectionStatus.OFFLINE)

    with pytest.raises(HumidifierProviderError) as captured:
        provider(FakeManager([device])).read_status()

    assert captured.value.code == "VESYNC_HUMIDIFIER_OFFLINE"
    assert captured.value.retryable is True


def test_rejects_unknown_device_state():
    device = fake_device(state=DeviceStatus.UNKNOWN)

    with pytest.raises(HumidifierProviderError) as captured:
        provider(FakeManager([device])).read_status()

    assert captured.value.code == "VESYNC_UNKNOWN_HUMIDIFIER_STATE"


def test_turns_device_on_using_allowlisted_power_operation():
    device = fake_device(state=DeviceStatus.OFF)

    provider(FakeManager([device])).set_state(HumidifierState.ON)

    device.turn_on.assert_awaited_once_with()
    device.turn_off.assert_not_awaited()


def test_does_not_repeat_command_when_cloud_already_reports_desired_state():
    device = fake_device(state=DeviceStatus.ON)

    provider(FakeManager([device])).set_state(HumidifierState.ON)

    device.turn_on.assert_not_awaited()
    device.turn_off.assert_not_awaited()


def test_reports_rejected_command():
    device = fake_device(state=DeviceStatus.ON)
    device.turn_off.return_value = False

    with pytest.raises(HumidifierProviderError) as captured:
        provider(FakeManager([device])).set_state(HumidifierState.OFF)

    assert captured.value.code == "VESYNC_COMMAND_REJECTED"


def test_common_controller_rereads_and_reports_unconfirmed_command():
    initial = fake_device(state=DeviceStatus.OFF)
    command_target = fake_device(state=DeviceStatus.OFF)
    still_off = fake_device(state=DeviceStatus.OFF)
    manager_factory = Mock(
        side_effect=[
            FakeManager([initial]),
            FakeManager([command_target]),
            FakeManager([still_off]),
        ]
    )
    target = VeSyncHumidifierProvider(
        username="parent@example.com",
        password="secret",
        humidifier_device_id="levoit-children",
        country_code="DE",
        time_zone="Europe/Berlin",
        timeout_seconds=15,
        manager_factory=manager_factory,
    )
    room = RoomConfig(
        "children-room",
        "quarto das criancas",
        "meter-children",
        True,
        HumidifierProviderKind.VESYNC,
        "levoit-children",
    )

    result = run_humidifier_control(
        room=room,
        relative_humidity=40,
        current_time=time(20),
        provider=target,
        dry_run=False,
    )

    assert result.command_attempted is True
    assert result.command_succeeded is True
    assert result.state_confirmed is False
    assert result.error_code == "HUMIDIFIER_STATE_NOT_CONFIRMED"
    command_target.turn_on.assert_awaited_once_with()
    assert manager_factory.call_count == 3


def test_reports_authentication_failure_without_leaking_credentials():
    with pytest.raises(HumidifierProviderError) as captured:
        provider(FakeManager(logged_in=False)).read_status()

    assert captured.value.code == "VESYNC_AUTHENTICATION_FAILED"
    assert "secret" not in captured.value.message


@pytest.mark.parametrize(
    "provider_error,expected_code,retryable",
    [
        (TimeoutError(), "VESYNC_TIMEOUT", True),
        (
            ClientConnectionError("offline"),
            "VESYNC_CONNECTION_ERROR",
            True,
        ),
    ],
)
def test_translates_transport_failures(provider_error, expected_code, retryable):
    manager = FakeManager()
    manager.login.side_effect = provider_error

    with pytest.raises(HumidifierProviderError) as captured:
        provider(manager).read_status()

    assert captured.value.code == expected_code
    assert captured.value.retryable is retryable


@pytest.mark.parametrize(
    "overrides",
    [
        {"username": ""},
        {"password": ""},
        {"humidifier_device_id": ""},
        {"timeout_seconds": 0},
        {"timeout_seconds": float("nan")},
    ],
)
def test_rejects_invalid_configuration(overrides):
    arguments = {
        "username": "parent@example.com",
        "password": "secret",
        "humidifier_device_id": "levoit-children",
        "country_code": "DE",
        "time_zone": "Europe/Berlin",
        "timeout_seconds": 15,
        **overrides,
    }

    with pytest.raises(ValueError):
        VeSyncHumidifierProvider(**arguments)
