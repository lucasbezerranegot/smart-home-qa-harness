import pytest

from smart_home_qa_harness.humidifier_provider import (
    HumidifierOperationState,
    HumidifierPowerCalibration,
    HumidifierProviderStatus,
    HumidifierState,
)


def test_accepts_confirmed_and_unconfirmed_provider_states():
    confirmed = HumidifierProviderStatus(
        "vesync",
        "children-humidifier",
        HumidifierState.ON,
        True,
    )
    unconfirmed = HumidifierProviderStatus(
        "unobservable-provider",
        "unobservable-device",
        HumidifierState.ON,
        False,
        False,
    )

    assert confirmed.state_confirmed is True
    assert unconfirmed.state_confirmed is False


def test_accepts_unknown_unconfirmed_state_for_non_observable_provider():
    result = HumidifierProviderStatus(
        "unobservable-provider",
        "unobservable-device",
        None,
        False,
        False,
    )

    assert result.reported_state is None


@pytest.mark.parametrize(
    "arguments",
    [
        ("", "device", HumidifierState.ON, True),
        ("provider", "", HumidifierState.ON, True),
        ("provider", "device", "ON", True),
        ("provider", "device", None, True),
        ("provider", "device", HumidifierState.ON, "yes"),
        ("provider", "device", HumidifierState.ON, True, False),
    ],
)
def test_rejects_malformed_common_status(arguments):
    with pytest.raises(ValueError):
        HumidifierProviderStatus(*arguments)


@pytest.mark.parametrize(
    "values",
    [
        (-0.1, 5, 15),
        (5, 5, 15),
        (0.5, 15, 5),
        (0.5, float("nan"), 15),
        (False, 5, 15),
    ],
)
def test_rejects_invalid_power_calibration(values):
    with pytest.raises(ValueError):
        HumidifierPowerCalibration(*values)


def test_accepts_confirmed_electrical_operation():
    result = HumidifierProviderStatus(
        "switchbot-plug",
        "plug",
        HumidifierState.ON,
        True,
        power_watts=7.2,
        operation_state=HumidifierOperationState.RUNNING,
        operation_confirmed=True,
        operation_confirmation_supported=True,
    )

    assert result.operation_state is HumidifierOperationState.RUNNING
    assert result.operation_confirmed is True
