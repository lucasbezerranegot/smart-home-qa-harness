from datetime import time

import pytest

from smart_home_qa_harness.decision_engine import WindowAction
from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentData,
)
from smart_home_qa_harness.room_config import RoomConfig
from smart_home_qa_harness.ventilation_engine import (
    VentilationReason,
    aggregate_ventilation_decisions,
    decide_room_ventilation,
)


def room(room_id, meter_id, has_window=True):
    return RoomConfig(room_id, room_id, meter_id, has_window)


def reading(meter_id, temperature, humidity):
    return IndoorEnvironmentData(
        temperature=temperature,
        relative_humidity=humidity,
        retrieved_at="2026-09-26T18:00:00+00:00",
        source=f"switchbot:{meter_id}",
    )


def test_preserves_room_identity_and_summer_reason():
    bedroom = room("bedroom", "meter-bedroom")

    result = decide_room_ventilation(
        room=bedroom,
        reading=reading("meter-bedroom", 25.0, 50.0),
        outside_temperature=18.0,
        daily_max_temperature=27.0,
        current_time=time(20),
    )

    assert result.room is bedroom
    assert result.action is WindowAction.OPEN_WINDOWS
    assert result.reason is VentilationReason.SUMMER_COOLING


def test_cool_day_uses_room_humidity():
    children = room("children-room", "meter-children")

    result = decide_room_ventilation(
        room=children,
        reading=reading("meter-children", 21.0, 65.0),
        outside_temperature=10.0,
        daily_max_temperature=18.0,
        current_time=time(8),
    )

    assert result.action is WindowAction.OPEN_WINDOWS
    assert result.reason is VentilationReason.HIGH_HUMIDITY


@pytest.mark.parametrize(
    "target_room,target_reading",
    [
        (room("bathroom", "meter-bath", False), reading("meter-bath", 22, 60)),
        (room("bedroom", "meter-bedroom"), reading("other-meter", 22, 60)),
        (
            room("bedroom", "meter-bedroom"),
            IndoorEnvironmentData(22, None, "now", "switchbot:meter-bedroom"),
        ),
    ],
)
def test_rejects_rooms_or_readings_that_cannot_drive_ventilation(
    target_room,
    target_reading,
):
    with pytest.raises(ValueError):
        decide_room_ventilation(
            room=target_room,
            reading=target_reading,
            outside_temperature=10,
            daily_max_temperature=18,
            current_time=time(8),
        )


def test_aggregates_all_matching_rooms_independently_of_read_order():
    children = room("children-room", "meter-children")
    living = room("living-room", "meter-living")
    decisions = tuple(
        decide_room_ventilation(
            room=target,
            reading=reading(target.meter_id, temperature, 50),
            outside_temperature=18,
            daily_max_temperature=27,
            current_time=time(20),
        )
        for target, temperature in ((living, 25), (children, 26))
    )

    result = aggregate_ventilation_decisions(decisions)

    assert len(result) == 1
    assert result[0].action is WindowAction.OPEN_WINDOWS
    assert result[0].rooms == (living, children)
