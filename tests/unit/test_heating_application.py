from datetime import datetime, timezone
from unittest.mock import patch

from smart_home_qa_harness.heating_application import (
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


def test_ignores_incomplete_disabled_zones():
    environ = heating_environment()
    for index in range(1, 6):
        prefix = f"HEATING_ZONE_{index}"
        environ[f"{prefix}_ENABLED"] = "false"
        environ[f"{prefix}_RELAY_ID"] = ""
        environ[f"{prefix}_METER_ID"] = ""

    result = load_heating_application_config(environ)

    assert [zone.name for zone in result.zones] == ["children-room"]
