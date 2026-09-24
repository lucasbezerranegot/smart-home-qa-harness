from dataclasses import dataclass
from enum import Enum


class MeterReadingStatus(Enum):
    VALID = "VALID"
    MISSING = "MISSING"
    INVALID = "INVALID"
    STALE = "STALE"


@dataclass(frozen=True)
class MeterReading:
    meter_id: str
    temperature: float | None
    status: MeterReadingStatus


def decide_heating_state(
    reading: MeterReading,
    previous_state: str,
    target_temperature: float,
    hysteresis: float,
) -> str:
    if reading.status is not MeterReadingStatus.VALID:
        return "OFF"

    if reading.temperature is None:
        return "OFF"

    turn_on_temperature = target_temperature - hysteresis

    if reading.temperature <= turn_on_temperature:
        return "ON"

    if reading.temperature >= target_temperature:
        return "OFF"

    return previous_state