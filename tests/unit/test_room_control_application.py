from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from smart_home_qa_harness.humidifier_provider import (
    HumidifierProviderStatus,
    HumidifierState,
)
from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentData,
    IndoorEnvironmentError,
)
from smart_home_qa_harness.room_control_application import (
    RoomControlApplicationError,
    load_room_control_config,
    run_room_control_cycle,
)
from smart_home_qa_harness.weather_client import WeatherData


ENVIRON = {
    "WEATHER_LATITUDE": "48.13",
    "WEATHER_LONGITUDE": "11.57",
    "SWITCHBOT_TOKEN": "token",
    "SWITCHBOT_SECRET": "secret",
    "ROOM_COUNT": "2",
    "ROOM_1_ID": "children-room",
    "ROOM_1_DISPLAY_NAME": "quarto das crianças",
    "ROOM_1_METER_ID": "meter-children",
    "ROOM_1_HAS_WINDOW": "true",
    "ROOM_1_HUMIDIFIER_PROVIDER": "switchbot-plug",
    "ROOM_1_HUMIDIFIER_DEVICE_ID": "plug-children",
    "ROOM_2_ID": "living-room",
    "ROOM_2_DISPLAY_NAME": "sala",
    "ROOM_2_METER_ID": "meter-living",
    "ROOM_2_HAS_WINDOW": "true",
}


def meter_reader(**arguments):
    temperatures = {"meter-children": 25.0, "meter-living": 26.0}
    return IndoorEnvironmentData(
        temperature=temperatures[arguments["device_id"]],
        relative_humidity=40.0,
        retrieved_at=arguments["retrieved_at"],
        source=f"switchbot:{arguments['device_id']}",
    )


def fake_provider(state=HumidifierState.OFF):
    result = Mock()
    result.provider_name = "switchbot-plug"
    result.device_id = "plug-children"
    result.read_status.return_value = HumidifierProviderStatus(
        result.provider_name,
        result.device_id,
        state,
        True,
    )
    return result


def test_one_cycle_reuses_room_registry_for_ventilation_and_humidifier():
    config = load_room_control_config(ENVIRON)
    weather = Mock(
        return_value=WeatherData(18, "2026-09-26T20:00", 27)
    )
    target = fake_provider()

    result = run_room_control_cycle(
        config=config,
        current_datetime=datetime(
            2026, 9, 26, 20, 0, tzinfo=ZoneInfo("Europe/Berlin")
        ),
        nonce_factory=Mock(side_effect=lambda: "nonce"),
        meter_reader=Mock(side_effect=meter_reader),
        weather_provider=weather,
        humidifier_provider_factory=Mock(return_value=target),
    )

    assert [
        room.room_id for room in result.ventilation.recommendations[0].rooms
    ] == ["children-room", "living-room"]
    assert len(result.humidifiers) == 1
    assert result.humidifiers[0].desired_state is HumidifierState.ON
    assert result.humidifiers[0].dry_run is True
    target.set_state.assert_not_called()


def test_missing_meter_is_reported_and_humidifier_fails_safe_to_off():
    config = load_room_control_config(ENVIRON)

    def failing_reader(**arguments):
        if arguments["device_id"] == "meter-children":
            raise IndoorEnvironmentError("METER_TIMEOUT", "timeout", True)
        return meter_reader(**arguments)

    result = run_room_control_cycle(
        config=config,
        current_datetime=datetime(
            2026, 9, 26, 20, 0, tzinfo=ZoneInfo("Europe/Berlin")
        ),
        meter_reader=failing_reader,
        weather_provider=Mock(return_value=WeatherData(18, "now", 27)),
        humidifier_provider_factory=Mock(
            return_value=fake_provider(HumidifierState.ON)
        ),
    )

    assert result.reading_failures[0].room_id == "children-room"
    assert result.humidifiers[0].desired_state is HumidifierState.OFF
    assert result.ventilation.failures[0].room_id == "children-room"


def test_does_not_fetch_weather_outside_ventilation_period():
    weather = Mock()
    result = run_room_control_cycle(
        config=load_room_control_config(ENVIRON),
        current_datetime=datetime(
            2026, 9, 26, 15, 0, tzinfo=ZoneInfo("Europe/Berlin")
        ),
        meter_reader=meter_reader,
        weather_provider=weather,
        humidifier_provider_factory=Mock(return_value=fake_provider()),
    )

    weather.assert_not_called()
    assert result.ventilation.recommendations == ()


def test_unavailable_provider_is_isolated_to_its_room():
    environ = {
        **ENVIRON,
        "ROOM_1_HUMIDIFIER_PROVIDER": "vesync",
        "ROOM_2_HUMIDIFIER_PROVIDER": "tinytuya-ir",
        "ROOM_2_HUMIDIFIER_DEVICE_ID": "remote-living",
    }

    result = run_room_control_cycle(
        config=load_room_control_config(environ),
        current_datetime=datetime(
            2026, 9, 26, 20, 0, tzinfo=ZoneInfo("Europe/Berlin")
        ),
        meter_reader=meter_reader,
        weather_provider=Mock(return_value=WeatherData(18, "now", 27)),
        humidifier_provider_factory=None,
    )

    assert len(result.humidifiers) == 2
    assert result.humidifiers[0].room_id == "children-room"
    assert (
        result.humidifiers[0].error_code
        == "UNSUPPORTED_HUMIDIFIER_PROVIDER"
    )
    assert result.humidifiers[1].room_id == "living-room"
    assert (
        result.humidifiers[1].error_code
        == "UNSUPPORTED_HUMIDIFIER_PROVIDER"
    )


def test_rejects_naive_datetime():
    with pytest.raises(RoomControlApplicationError) as captured:
        run_room_control_cycle(
            config=load_room_control_config(ENVIRON),
            current_datetime=datetime(2026, 9, 26, 20),
        )

    assert captured.value.code == "INVALID_CURRENT_DATETIME"


@pytest.mark.parametrize(
    "environ",
    [
        {},
        {**ENVIRON, "WEATHER_LATITUDE": "north"},
        {**ENVIRON, "SWITCHBOT_TOKEN": ""},
    ],
)
def test_rejects_invalid_application_configuration(environ):
    with pytest.raises(RoomControlApplicationError):
        load_room_control_config(environ)
