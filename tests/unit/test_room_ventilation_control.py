from datetime import time

from smart_home_qa_harness.decision_engine import WindowAction
from smart_home_qa_harness.inside_environment_client import IndoorEnvironmentData
from smart_home_qa_harness.room_config import HomeRoomConfig, RoomConfig
from smart_home_qa_harness.room_ventilation_control import (
    evaluate_home_ventilation,
)


def reading(meter_id, temperature, humidity):
    return IndoorEnvironmentData(
        temperature,
        humidity,
        "2026-09-26T18:00:00+00:00",
        f"switchbot:{meter_id}",
    )


def test_evaluates_every_window_room_before_building_one_recommendation():
    children = RoomConfig("children", "crianças", "meter-c", True)
    living = RoomConfig("living", "sala", "meter-l", True)
    bathroom = RoomConfig("bath", "banheiro", "meter-b", False)
    home = HomeRoomConfig((children, living, bathroom))

    result = evaluate_home_ventilation(
        home=home,
        readings={
            "children": reading("meter-c", 25, 50),
            "living": reading("meter-l", 26, 50),
            "bath": reading("meter-b", 30, 80),
        },
        outside_temperature=18,
        daily_max_temperature=27,
        current_time=time(20),
    )

    assert [decision.room.room_id for decision in result.decisions] == [
        "children",
        "living",
    ]
    assert result.recommendations[0].action is WindowAction.OPEN_WINDOWS
    assert [
        room.room_id for room in result.recommendations[0].rooms
    ] == ["children", "living"]
    assert result.failures == ()


def test_one_missing_room_does_not_block_other_rooms():
    children = RoomConfig("children", "crianças", "meter-c", True)
    living = RoomConfig("living", "sala", "meter-l", True)

    result = evaluate_home_ventilation(
        home=HomeRoomConfig((children, living)),
        readings={"living": reading("meter-l", 25, 50)},
        outside_temperature=18,
        daily_max_temperature=27,
        current_time=time(20),
    )

    assert [decision.room.room_id for decision in result.decisions] == [
        "living"
    ]
    assert result.failures[0].room_id == "children"
    assert result.failures[0].error_code == "MISSING_ROOM_READING"
