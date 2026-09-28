import pytest

from smart_home_qa_harness.room_config import (
    HomeRoomConfig,
    RoomConfig,
    RoomConfigurationError,
    load_room_config,
)


def room(room_id, meter_id, has_window=True, plug_id=None):
    return RoomConfig(
        room_id=room_id,
        display_name=room_id.replace("-", " "),
        meter_id=meter_id,
        has_window=has_window,
        humidifier_plug_id=plug_id,
    )


def test_home_config_exposes_rooms_by_capability():
    children = room("children-room", "meter-1", plug_id="plug-1")
    living = room("living-room", "meter-2")
    bathroom = room("bathroom", "meter-3", has_window=False)

    result = HomeRoomConfig((children, living, bathroom))

    assert result.ventilation_rooms == (children, living)
    assert result.humidifier_rooms == (children,)


def test_loads_numbered_room_configuration():
    environ = {
        "ROOM_COUNT": "2",
        "ROOM_1_ID": "children-room",
        "ROOM_1_DISPLAY_NAME": "quarto das crianças",
        "ROOM_1_METER_ID": "meter-children",
        "ROOM_1_HAS_WINDOW": "true",
        "ROOM_1_HUMIDIFIER_PLUG_ID": "plug-children",
        "ROOM_2_ID": "bathroom",
        "ROOM_2_DISPLAY_NAME": "banheiro",
        "ROOM_2_METER_ID": "meter-bathroom",
        "ROOM_2_HAS_WINDOW": "false",
    }

    result = load_room_config(environ)

    assert result.rooms[0].humidifier_plug_id == "plug-children"
    assert result.rooms[1].humidifier_plug_id is None
    assert result.ventilation_rooms == (result.rooms[0],)


@pytest.mark.parametrize(
    "field,value",
    [
        ("room_id", ""),
        ("display_name", "   "),
        ("meter_id", None),
        ("has_window", "true"),
        ("humidifier_plug_id", ""),
    ],
)
def test_rejects_invalid_room_fields(field, value):
    arguments = {
        "room_id": "bedroom",
        "display_name": "quarto",
        "meter_id": "meter-bedroom",
        "has_window": True,
        "humidifier_plug_id": None,
    }
    arguments[field] = value

    with pytest.raises(RoomConfigurationError) as captured:
        RoomConfig(**arguments)

    assert captured.value.code == "INVALID_ROOM_CONFIGURATION"


@pytest.mark.parametrize(
    "rooms",
    [
        (
            room("bedroom", "meter-1"),
            room("bedroom", "meter-2"),
        ),
        (
            room("bedroom", "meter-1"),
            room("living-room", "meter-1"),
        ),
        (
            room("bedroom", "meter-1", plug_id="plug-1"),
            room("children-room", "meter-2", plug_id="plug-1"),
        ),
    ],
)
def test_rejects_duplicate_room_device_assignments(rooms):
    with pytest.raises(RoomConfigurationError) as captured:
        HomeRoomConfig(rooms)

    assert captured.value.code == "DUPLICATE_ROOM_DEVICE"


@pytest.mark.parametrize(
    "environ,code",
    [
        ({}, "MISSING_ROOM_CONFIGURATION"),
        ({"ROOM_COUNT": "zero"}, "INVALID_ROOM_CONFIGURATION"),
        ({"ROOM_COUNT": "0"}, "INVALID_ROOM_CONFIGURATION"),
        (
            {
                "ROOM_COUNT": "1",
                "ROOM_1_ID": "bedroom",
            },
            "MISSING_ROOM_CONFIGURATION",
        ),
        (
            {
                "ROOM_COUNT": "1",
                "ROOM_1_ID": "bedroom",
                "ROOM_1_DISPLAY_NAME": "quarto",
                "ROOM_1_METER_ID": "meter",
                "ROOM_1_HAS_WINDOW": "yes",
            },
            "INVALID_ROOM_CONFIGURATION",
        ),
    ],
)
def test_rejects_invalid_environment_configuration(environ, code):
    with pytest.raises(RoomConfigurationError) as captured:
        load_room_config(environ)

    assert captured.value.code == code
