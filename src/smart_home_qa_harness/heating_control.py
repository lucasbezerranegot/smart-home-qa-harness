from dataclasses import dataclass
import math

from smart_home_qa_harness.heating_engine import (
    MeterReading,
    MeterReadingStatus,
    decide_heating_state,
)


class HeatingConfigurationError(ValueError):
    """Non-retryable heating configuration validation failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = False


@dataclass(frozen=True)
class HeatingConfiguration:
    relay_id: str
    meter_id: str
    target_temperature: float
    hysteresis: float

    def __post_init__(self):
        if not isinstance(self.relay_id, str) or not self.relay_id.strip():
            raise HeatingConfigurationError(
                code="INVALID_RELAY_ID",
                message="Relay ID must be a non-empty string.",
            )

        if not isinstance(self.meter_id, str) or not self.meter_id.strip():
            raise HeatingConfigurationError(
                code="INVALID_METER_ID",
                message="Meter ID must be a non-empty string.",
            )

        if not _is_finite_number(self.target_temperature):
            raise HeatingConfigurationError(
                code="INVALID_TARGET_TEMPERATURE",
                message="Target temperature must be a finite number.",
            )

        if not _is_finite_number(self.hysteresis) or self.hysteresis < 0:
            raise HeatingConfigurationError(
                code="INVALID_HYSTERESIS",
                message="Hysteresis must be a finite non-negative number.",
            )


def decide_relay_state(
    configuration: HeatingConfiguration,
    readings: list[MeterReading],
    previous_state: str,
) -> str:
    associated_reading = next(
        (
            reading
            for reading in readings
            if reading.meter_id == configuration.meter_id
        ),
        MeterReading(
            meter_id=configuration.meter_id,
            temperature=None,
            status=MeterReadingStatus.MISSING,
        ),
    )

    return decide_heating_state(
        reading=associated_reading,
        previous_state=previous_state,
        target_temperature=configuration.target_temperature,
        hysteresis=configuration.hysteresis,
    )


def _is_finite_number(value) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )
