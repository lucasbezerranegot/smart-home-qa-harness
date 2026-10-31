from unittest.mock import Mock, patch

import pytest

from smart_home_qa_harness.humidifier_provider import (
    HumidifierOperationState,
    HumidifierPowerCalibration,
    HumidifierProviderError,
    HumidifierState,
)
from smart_home_qa_harness.switchbot_humidifier_provider import (
    SwitchBotPlugHumidifierProvider,
)
from smart_home_qa_harness.switchbot_plug_client import (
    PlugMiniStatus,
    PlugState,
    SwitchBotPlugError,
)


def provider(power_calibration=None):
    return SwitchBotPlugHumidifierProvider(
        token="secret-token",
        secret="secret-key",
        plug_device_id="plug-children",
        timestamp_ms=1724000000000,
        nonce_factory=Mock(return_value="nonce"),
        power_calibration=power_calibration,
    )


@patch("smart_home_qa_harness.switchbot_humidifier_provider.get_plug_status")
def test_translates_switchbot_status_to_common_contract(get_status):
    get_status.return_value = PlugMiniStatus(
        "plug-children",
        PlugState.ON,
        230,
        20,
        90,
        120,
    )

    result = provider().read_status()

    assert result.provider_name == "switchbot-plug"
    assert result.device_id == "plug-children"
    assert result.reported_state is HumidifierState.ON
    assert result.state_confirmed is True
    assert result.power_watts == 20


@patch("smart_home_qa_harness.switchbot_humidifier_provider.set_plug_state")
def test_translates_common_command_to_switchbot_state(set_state):
    target = provider()

    target.set_state(HumidifierState.OFF)

    assert set_state.call_args.kwargs["state"] is PlugState.OFF
    assert set_state.call_args.kwargs["device_id"] == "plug-children"


@pytest.mark.parametrize("operation", ["read", "write"])
def test_translates_switchbot_errors_to_common_error(operation):
    target = provider()
    error = SwitchBotPlugError("SWITCHBOT_FAILED", "failed", True)
    patch_target = (
        "smart_home_qa_harness.switchbot_humidifier_provider.get_plug_status"
        if operation == "read"
        else "smart_home_qa_harness.switchbot_humidifier_provider.set_plug_state"
    )

    with patch(patch_target, side_effect=error):
        with pytest.raises(HumidifierProviderError) as captured:
            if operation == "read":
                target.read_status()
            else:
                target.set_state(HumidifierState.ON)

    assert captured.value.code == "SWITCHBOT_FAILED"
    assert captured.value.retryable is True


def test_rejects_non_common_state_before_switchbot_call():
    with pytest.raises(HumidifierProviderError) as captured:
        provider().set_state("ON")

    assert captured.value.code == "INVALID_HUMIDIFIER_STATE"


@pytest.mark.parametrize(
    "relay_state,power,expected_state,confirmed",
    [
        (PlugState.OFF, 0.0, HumidifierOperationState.OFF, True),
        (PlugState.ON, 0.4, HumidifierOperationState.OFF, True),
        (PlugState.ON, 5.0, HumidifierOperationState.RUNNING, True),
        (PlugState.ON, 15.0, HumidifierOperationState.RUNNING, True),
        (PlugState.ON, 2.0, HumidifierOperationState.AMBIGUOUS, False),
        (PlugState.ON, 20.0, HumidifierOperationState.AMBIGUOUS, False),
    ],
)
@patch("smart_home_qa_harness.switchbot_humidifier_provider.get_plug_status")
def test_classifies_electrically_observed_operation(
    get_status,
    relay_state,
    power,
    expected_state,
    confirmed,
):
    get_status.return_value = PlugMiniStatus(
        "plug-children",
        relay_state,
        230,
        power,
        90,
        120,
    )
    target = provider(HumidifierPowerCalibration(0.5, 5.0, 15.0))

    result = target.read_status()

    assert result.operation_confirmation_supported is True
    assert result.operation_state is expected_state
    assert result.operation_confirmed is confirmed


@patch("smart_home_qa_harness.switchbot_humidifier_provider.get_plug_status")
def test_leaves_operation_confirmation_disabled_without_calibration(get_status):
    get_status.return_value = PlugMiniStatus(
        "plug-children",
        PlugState.ON,
        230,
        7.2,
        90,
        120,
    )

    result = provider().read_status()

    assert result.operation_confirmation_supported is False
    assert result.operation_state is None
    assert result.operation_confirmed is False
