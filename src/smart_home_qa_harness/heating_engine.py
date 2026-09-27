from dataclasses import dataclass
from enum import Enum
import math


class HeatingEngineError(ValueError):
    """Non-retryable domain validation failure in heating decisions."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = False


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

    def __post_init__(self):
        if not isinstance(self.meter_id, str) or not self.meter_id.strip():
            raise HeatingEngineError(
                code="INVALID_METER_ID",
                message="Meter ID must be a non-empty string.",
            )

        if not isinstance(self.status, MeterReadingStatus):
            raise HeatingEngineError(
                code="INVALID_READING_STATUS",
                message="Meter reading status is invalid.",
            )

        if self.status is MeterReadingStatus.VALID and not _is_finite_number(
            self.temperature
        ):
            raise HeatingEngineError(
                code="INVALID_METER_TEMPERATURE",
                message="A valid Meter reading requires a finite temperature.",
            )


def decide_heating_state(
    reading: MeterReading,
    previous_state: str,
    target_temperature: float,
    hysteresis: float,
) -> str:
    if not isinstance(reading, MeterReading):
        raise HeatingEngineError(
            code="INVALID_METER_READING",
            message="A MeterReading instance is required.",
        )

    if previous_state not in {"ON", "OFF"}:
        raise HeatingEngineError(
            code="INVALID_PREVIOUS_STATE",
            message="Previous relay state must be ON or OFF.",
        )

    if not _is_finite_number(target_temperature):
        raise HeatingEngineError(
            code="INVALID_TARGET_TEMPERATURE",
            message="Target temperature must be a finite number.",
        )

    if not _is_finite_number(hysteresis) or hysteresis < 0:
        raise HeatingEngineError(
            code="INVALID_HYSTERESIS",
            message="Hysteresis must be a finite non-negative number.",
        )

    if reading.status is not MeterReadingStatus.VALID:
        return "OFF"

    turn_on_temperature = target_temperature - hysteresis

    if reading.temperature <= turn_on_temperature:
        return "ON"

    if reading.temperature >= target_temperature:
        return "OFF"

    return previous_state


def _is_finite_number(value) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )
