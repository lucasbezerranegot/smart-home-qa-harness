import pytest

from smart_home_qa_harness.humidifier_provider import (
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
