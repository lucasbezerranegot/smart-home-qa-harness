from datetime import datetime, timedelta, timezone

import pytest

from smart_home_qa_harness.heating_engine import MeterReadingStatus
from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentData,
    IndoorEnvironmentError,
)
from smart_home_qa_harness.meter_reading_adapter import (
    MeterReadingAdapterError,
    meter_reading_from_client_error,
    to_meter_reading,
)


CURRENT_DATETIME = datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc)
METER_ID = "children-room-meter"


def environment_data(
    temperature=22.0,
    retrieved_at="2026-09-24T17:55:00+00:00",
    source=f"switchbot:{METER_ID}",
):
    return IndoorEnvironmentData(
        temperature=temperature,
        relative_humidity=50.0,
        retrieved_at=retrieved_at,
        source=source,
    )


def test_converts_recent_switchbot_data_to_valid_meter_reading():
    result = to_meter_reading(
        environment_data=environment_data(),
        expected_meter_id=METER_ID,
        current_datetime=CURRENT_DATETIME,
        maximum_age=timedelta(minutes=10),
    )

    assert result.meter_id == METER_ID
    assert result.temperature == 22.0
    assert result.status is MeterReadingStatus.VALID


def test_accepts_reading_at_exact_maximum_age():
    result = to_meter_reading(
        environment_data=environment_data(
            retrieved_at="2026-09-24T17:50:00+00:00"
        ),
        expected_meter_id=METER_ID,
        current_datetime=CURRENT_DATETIME,
        maximum_age=timedelta(minutes=10),
    )

    assert result.status is MeterReadingStatus.VALID


def test_marks_reading_older_than_maximum_age_as_stale():
    result = to_meter_reading(
        environment_data=environment_data(
            retrieved_at="2026-09-24T17:49:59+00:00"
        ),
        expected_meter_id=METER_ID,
        current_datetime=CURRENT_DATETIME,
        maximum_age=timedelta(minutes=10),
    )

    assert result.temperature is None
    assert result.status is MeterReadingStatus.STALE


@pytest.mark.parametrize(
    "retrieved_at",
    ["not-a-date", "2026-09-24T17:55:00", None],
)
def test_marks_invalid_retrieval_timestamp_as_invalid(retrieved_at):
    result = to_meter_reading(
        environment_data=environment_data(retrieved_at=retrieved_at),
        expected_meter_id=METER_ID,
        current_datetime=CURRENT_DATETIME,
        maximum_age=timedelta(minutes=10),
    )

    assert result.status is MeterReadingStatus.INVALID


def test_marks_future_retrieval_timestamp_as_invalid():
    result = to_meter_reading(
        environment_data=environment_data(
            retrieved_at="2026-09-24T18:00:01+00:00"
        ),
        expected_meter_id=METER_ID,
        current_datetime=CURRENT_DATETIME,
        maximum_age=timedelta(minutes=10),
    )

    assert result.status is MeterReadingStatus.INVALID


def test_handles_equivalent_timestamps_in_different_timezones():
    result = to_meter_reading(
        environment_data=environment_data(
            retrieved_at="2026-09-24T19:55:00+02:00"
        ),
        expected_meter_id=METER_ID,
        current_datetime=CURRENT_DATETIME,
        maximum_age=timedelta(minutes=10),
    )

    assert result.status is MeterReadingStatus.VALID


def test_rejects_data_from_another_meter():
    result = to_meter_reading(
        environment_data=environment_data(source="switchbot:another-meter"),
        expected_meter_id=METER_ID,
        current_datetime=CURRENT_DATETIME,
        maximum_age=timedelta(minutes=10),
    )

    assert result.status is MeterReadingStatus.INVALID


@pytest.mark.parametrize("temperature", [None, True, "22", float("nan"), float("inf")])
def test_marks_invalid_temperature_as_invalid(temperature):
    result = to_meter_reading(
        environment_data=environment_data(temperature=temperature),
        expected_meter_id=METER_ID,
        current_datetime=CURRENT_DATETIME,
        maximum_age=timedelta(minutes=10),
    )

    assert result.status is MeterReadingStatus.INVALID


@pytest.mark.parametrize(
    ("retryable", "expected_status"),
    [
        (True, MeterReadingStatus.MISSING),
        (False, MeterReadingStatus.INVALID),
    ],
)
def test_translates_client_error_to_safe_reading(retryable, expected_status):
    error = IndoorEnvironmentError(
        code="SWITCHBOT_FAILURE",
        message="SwitchBot failed.",
        retryable=retryable,
    )

    result = meter_reading_from_client_error(
        error=error,
        expected_meter_id=METER_ID,
    )

    assert result.temperature is None
    assert result.status is expected_status


@pytest.mark.parametrize("expected_meter_id", ["", "   ", None, 123])
def test_rejects_invalid_expected_meter_id(expected_meter_id):
    with pytest.raises(MeterReadingAdapterError) as captured:
        to_meter_reading(
            environment_data=environment_data(),
            expected_meter_id=expected_meter_id,
            current_datetime=CURRENT_DATETIME,
            maximum_age=timedelta(minutes=10),
        )

    assert captured.value.code == "INVALID_EXPECTED_METER_ID"


@pytest.mark.parametrize(
    "current_datetime",
    [None, "2026-09-24T18:00:00+00:00", datetime(2026, 9, 24, 18, 0)],
)
def test_rejects_invalid_current_datetime(current_datetime):
    with pytest.raises(MeterReadingAdapterError) as captured:
        to_meter_reading(
            environment_data=environment_data(),
            expected_meter_id=METER_ID,
            current_datetime=current_datetime,
            maximum_age=timedelta(minutes=10),
        )

    assert captured.value.code == "INVALID_CURRENT_DATETIME"


@pytest.mark.parametrize("maximum_age", [None, 600, timedelta(seconds=-1)])
def test_rejects_invalid_maximum_age(maximum_age):
    with pytest.raises(MeterReadingAdapterError) as captured:
        to_meter_reading(
            environment_data=environment_data(),
            expected_meter_id=METER_ID,
            current_datetime=CURRENT_DATETIME,
            maximum_age=maximum_age,
        )

    assert captured.value.code == "INVALID_MAXIMUM_AGE"
