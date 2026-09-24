from dataclasses import dataclass

from smart_home_qa_harness.heating_engine import (
    MeterReading,
    MeterReadingStatus,
    decide_heating_state,
)


@dataclass(frozen=True)
class HeatingConfiguration:
    relay_id: str
    meter_id: str
    target_temperature: float
    hysteresis: float


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