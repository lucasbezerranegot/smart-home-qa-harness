from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch

import pytest

from smart_home_qa_harness.heating_application import (
    HeatingApplicationConfigurationError,
    load_heating_application_config,
    run_switchbot_heating_zone,
)
from smart_home_qa_harness.inside_environment_client import IndoorEnvironmentData
from smart_home_qa_harness.switchbot_relay_client import (
    RelayChannelStatus,
    RelayState,
)


def heating_environment():
    environ = {
        "SWITCHBOT_TOKEN": "fake-token",
        "SWITCHBOT_SECRET": "fake-secret",
        "HEATING_MAXIMUM_READING_AGE_SECONDS": "600",
    }
    names = [
        "shower-bathroom",
        "kitchen",
        "living-room",
        "bathtub-bathroom",
        "bedroom",
        "children-room",
    ]
    for index, name in enumerate(names, start=1):
        relay_number = ((index - 1) // 2) + 1
        channel = 1 if index % 2 else 2
        prefix = f"HEATING_ZONE_{index}"
        environ.update(
            {
                f"{prefix}_NAME": name,
                f"{prefix}_ENABLED": "true",
                f"{prefix}_RELAY_ID": f"relay-{relay_number}",
                f"{prefix}_CHANNEL": str(channel),
                f"{prefix}_METER_ID": f"meter-{index}",
                f"{prefix}_TARGET_TEMPERATURE": "20",
                f"{prefix}_HYSTERESIS": "0.5",
            }
        )
    return environ


def test_loads_six_zones_across_three_dual_channel_relays():
    result = load_heating_application_config(heating_environment())

    assert len(result.zones) == 6
    assert [zone.configuration.relay_id for zone in result.zones] == [
        "relay-1",
        "relay-1",
        "relay-2",
        "relay-2",
        "relay-3",
        "relay-3",
    ]
    assert [zone.configuration.channel for zone in result.zones] == [
        1,
        2,
        1,
        2,
        1,
        2,
    ]
    assert result.zones[-1].name == "children-room"
    assert result.zones[-1].configuration.meter_id == "meter-6"


def test_selects_daily_temperature_profile_by_local_wall_clock():
    environ = heating_environment()
    environ["HEATING_ZONE_6_TEMPERATURE_PROFILE"] = (
        "19:00=17,02:00=18,07:00=20"
    )
    zone = load_heating_application_config(environ).zones[-1]
    berlin = ZoneInfo("Europe/Berlin")

    assert zone.configuration_at(
        datetime(2026, 11, 17, 1, 59, tzinfo=berlin)
    ).target_temperature == 17
    assert zone.configuration_at(
        datetime(2026, 11, 17, 2, 0, tzinfo=berlin)
    ).target_temperature == 18
    assert zone.configuration_at(
        datetime(2026, 11, 17, 7, 0, tzinfo=berlin)
    ).target_temperature == 20
    assert zone.configuration_at(
        datetime(2026, 11, 17, 19, 0, tzinfo=berlin)
    ).target_temperature == 17


def test_empty_temperature_profile_preserves_fixed_target():
    zone = load_heating_application_config(heating_environment()).zones[-1]

    assert zone.configuration_at(
        datetime(2026, 11, 17, 23, 0, tzinfo=timezone.utc)
    ).target_temperature == 20


@pytest.mark.parametrize(
    "profile",
    [
        "19:00-17",
        "19:00=17,19:00=18",
        "9:00=17",
        "19:00:01=17",
        "19:00+01:00=17",
        "not-a-time=17",
        "19:00=not-a-number",
        "19:00=nan",
        "19:00=15.9",
    ],
)
def test_rejects_invalid_temperature_profile(profile):
    environ = heating_environment()
    environ["HEATING_ZONE_6_TEMPERATURE_PROFILE"] = profile

    with pytest.raises(HeatingApplicationConfigurationError) as captured:
        load_heating_application_config(environ)

    assert captured.value.code == "INVALID_HEATING_CONFIGURATION"


def test_rejects_fixed_target_below_safety_minimum():
    environ = heating_environment()
    environ["HEATING_MINIMUM_TARGET_TEMPERATURE"] = "18"
    environ["HEATING_ZONE_6_TARGET_TEMPERATURE"] = "17"

    with pytest.raises(HeatingApplicationConfigurationError) as captured:
        load_heating_application_config(environ)

    assert captured.value.code == "INVALID_HEATING_CONFIGURATION"


@patch("smart_home_qa_harness.heating_application.set_relay_channel_state")
@patch("smart_home_qa_harness.heating_application.get_relay_channel_status")
@patch("smart_home_qa_harness.heating_application.get_switchbot_indoor_environment")
def test_children_zone_dry_run_decides_off_without_sending_command(
    get_environment,
    get_relay_status,
    set_relay_state,
):
    now = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
    config = load_heating_application_config(heating_environment())
    children_zone = config.zones[-1]
    get_environment.return_value = IndoorEnvironmentData(
        temperature=22.0,
        relative_humidity=50.0,
        retrieved_at=now.isoformat(),
        source="switchbot:meter-6",
    )
    get_relay_status.return_value = RelayChannelStatus(
        device_id="relay-3",
        channel=2,
        state=RelayState.ON,
        online=True,
    )

    result = run_switchbot_heating_zone(
        application_config=config,
        zone=children_zone,
        current_datetime=now,
        nonce_factory=lambda: "fake-nonce",
    )

    assert result.previous_state is RelayState.ON
    assert result.desired_state is RelayState.OFF
    assert result.command_sent is False
    set_relay_state.assert_not_called()


@patch("smart_home_qa_harness.heating_application.run_heating_control")
@patch("smart_home_qa_harness.heating_application.get_relay_channel_status")
@patch("smart_home_qa_harness.heating_application.get_switchbot_indoor_environment")
def test_run_uses_profile_target_active_at_cycle_time(
    get_environment,
    get_relay_status,
    run_control,
):
    now = datetime(
        2026, 11, 17, 20, 0, tzinfo=ZoneInfo("Europe/Berlin")
    )
    environ = heating_environment()
    environ["HEATING_ZONE_6_TEMPERATURE_PROFILE"] = "19:00=17,07:00=20"
    config = load_heating_application_config(environ)
    get_environment.return_value = IndoorEnvironmentData(
        temperature=18.0,
        relative_humidity=50.0,
        retrieved_at=now.isoformat(),
        source="switchbot:meter-6",
    )
    get_relay_status.return_value = RelayChannelStatus(
        device_id="relay-3",
        channel=2,
        state=RelayState.OFF,
        online=True,
    )

    run_switchbot_heating_zone(
        application_config=config,
        zone=config.zones[-1],
        current_datetime=now,
    )

    assert run_control.call_args.kwargs[
        "configuration"
    ].target_temperature == 17


def test_ignores_incomplete_disabled_zones():
    environ = heating_environment()
    for index in range(1, 6):
        prefix = f"HEATING_ZONE_{index}"
        environ[f"{prefix}_ENABLED"] = "false"
        environ[f"{prefix}_RELAY_ID"] = ""
        environ[f"{prefix}_METER_ID"] = ""

    result = load_heating_application_config(environ)

    assert [zone.name for zone in result.zones] == ["children-room"]


def test_rejects_duplicate_enabled_zone_names():
    environ = heating_environment()
    environ["HEATING_ZONE_2_NAME"] = environ["HEATING_ZONE_1_NAME"]

    with pytest.raises(HeatingApplicationConfigurationError) as captured:
        load_heating_application_config(environ)

    assert captured.value.code == "DUPLICATE_HEATING_ZONE_NAME"


def test_rejects_duplicate_enabled_relay_channel_assignments():
    environ = heating_environment()
    environ["HEATING_ZONE_2_CHANNEL"] = "1"

    with pytest.raises(HeatingApplicationConfigurationError) as captured:
        load_heating_application_config(environ)

    assert captured.value.code == "DUPLICATE_HEATING_RELAY_CHANNEL"


def test_allows_zones_to_share_a_meter_when_relay_channels_are_distinct():
    environ = heating_environment()
    environ["HEATING_ZONE_3_METER_ID"] = environ["HEATING_ZONE_2_METER_ID"]

    result = load_heating_application_config(environ)

    assert result.zones[1].configuration.meter_id == "meter-2"
    assert result.zones[2].configuration.meter_id == "meter-2"
