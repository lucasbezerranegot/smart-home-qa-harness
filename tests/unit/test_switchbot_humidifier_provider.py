from unittest.mock import Mock, patch

import pytest

from smart_home_qa_harness.humidifier_provider import (
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


def provider():
    return SwitchBotPlugHumidifierProvider(
        token="secret-token",
        secret="secret-key",
        plug_device_id="plug-children",
        timestamp_ms=1724000000000,
        nonce_factory=Mock(return_value="nonce"),
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
