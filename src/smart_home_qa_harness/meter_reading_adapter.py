"""Translate indoor-environment client results into heating-domain readings."""

from datetime import datetime, timedelta

from smart_home_qa_harness.heating_engine import (
    HeatingEngineError,
    MeterReading,
    MeterReadingStatus,
)
from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentData,
    IndoorEnvironmentError,
)


class MeterReadingAdapterError(ValueError):
    """Non-retryable programming or adapter configuration failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = False


def to_meter_reading(
    environment_data: IndoorEnvironmentData,
    expected_meter_id: str,
    current_datetime: datetime,
    maximum_age: timedelta,
) -> MeterReading:
    """Convert normalized SwitchBot data into a safe heating-domain reading."""

    _validate_adapter_inputs(
        expected_meter_id=expected_meter_id,
        current_datetime=current_datetime,
        maximum_age=maximum_age,
    )

    if not isinstance(environment_data, IndoorEnvironmentData):
        return _unsafe_reading(expected_meter_id, MeterReadingStatus.INVALID)

    if environment_data.source != f"switchbot:{expected_meter_id}":
        return _unsafe_reading(expected_meter_id, MeterReadingStatus.INVALID)

    try:
        retrieved_at = datetime.fromisoformat(environment_data.retrieved_at)
    except (TypeError, ValueError):
        return _unsafe_reading(expected_meter_id, MeterReadingStatus.INVALID)

    if retrieved_at.tzinfo is None:
        return _unsafe_reading(expected_meter_id, MeterReadingStatus.INVALID)

    age = current_datetime - retrieved_at
    if age < timedelta(0):
        return _unsafe_reading(expected_meter_id, MeterReadingStatus.INVALID)

    if age > maximum_age:
        return _unsafe_reading(expected_meter_id, MeterReadingStatus.STALE)

    try:
        return MeterReading(
            meter_id=expected_meter_id,
            temperature=environment_data.temperature,
            status=MeterReadingStatus.VALID,
        )
    except HeatingEngineError:
        return _unsafe_reading(expected_meter_id, MeterReadingStatus.INVALID)


def meter_reading_from_client_error(
    error: IndoorEnvironmentError,
    expected_meter_id: str,
) -> MeterReading:
    """Translate provider failures without leaking client exceptions downstream."""

    if not isinstance(expected_meter_id, str) or not expected_meter_id.strip():
        raise MeterReadingAdapterError(
            code="INVALID_EXPECTED_METER_ID",
            message="Expected Meter ID must be a non-empty string.",
        )

    if not isinstance(error, IndoorEnvironmentError):
        raise MeterReadingAdapterError(
            code="INVALID_CLIENT_ERROR",
            message="An IndoorEnvironmentError instance is required.",
        )

    status = (
        MeterReadingStatus.MISSING
        if error.retryable
        else MeterReadingStatus.INVALID
    )
    return _unsafe_reading(expected_meter_id, status)


def _validate_adapter_inputs(
    expected_meter_id: str,
    current_datetime: datetime,
    maximum_age: timedelta,
) -> None:
    if not isinstance(expected_meter_id, str) or not expected_meter_id.strip():
        raise MeterReadingAdapterError(
            code="INVALID_EXPECTED_METER_ID",
            message="Expected Meter ID must be a non-empty string.",
        )

    if (
        not isinstance(current_datetime, datetime)
        or current_datetime.tzinfo is None
    ):
        raise MeterReadingAdapterError(
            code="INVALID_CURRENT_DATETIME",
            message="Current datetime must include timezone information.",
        )

    if (
        not isinstance(maximum_age, timedelta)
        or maximum_age < timedelta(0)
    ):
        raise MeterReadingAdapterError(
            code="INVALID_MAXIMUM_AGE",
            message="Maximum age must be a non-negative timedelta.",
        )


def _unsafe_reading(
    meter_id: str,
    status: MeterReadingStatus,
) -> MeterReading:
    return MeterReading(
        meter_id=meter_id,
        temperature=None,
        status=status,
    )
