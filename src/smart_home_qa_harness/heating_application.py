"""Operational wiring for SwitchBot Meter-to-relay heating control."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid

from smart_home_qa_harness.heating_control import HeatingConfiguration
from smart_home_qa_harness.heating_orchestrator import (
    HeatingOrchestrationResult,
    run_heating_control,
)
from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentError,
    get_switchbot_indoor_environment,
)
from smart_home_qa_harness.meter_reading_adapter import (
    meter_reading_from_client_error,
    to_meter_reading,
)
from smart_home_qa_harness.switchbot_relay_client import (
    get_relay_channel_status,
    set_relay_channel_state,
)


@dataclass(frozen=True)
class HeatingZone:
    name: str
    configuration: HeatingConfiguration


@dataclass(frozen=True)
class HeatingApplicationConfig:
    switchbot_token: str
    switchbot_secret: str
    maximum_reading_age: timedelta
    zones: tuple[HeatingZone, ...]


class HeatingApplicationConfigurationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = False


def load_heating_application_config(
    environ: Mapping[str, str],
) -> HeatingApplicationConfig:
    try:
        token = environ["SWITCHBOT_TOKEN"]
        secret = environ["SWITCHBOT_SECRET"]
        maximum_age_seconds = int(
            environ.get("HEATING_MAXIMUM_READING_AGE_SECONDS", "600")
        )
        zones = tuple(
            _load_zone(environ, index)
            for index in range(1, 7)
            if _zone_is_enabled(environ, index)
        )
    except KeyError as error:
        raise HeatingApplicationConfigurationError(
            "MISSING_HEATING_CONFIGURATION",
            f"Missing required configuration: {error.args[0]}",
        ) from error
    except (TypeError, ValueError) as error:
        raise HeatingApplicationConfigurationError(
            "INVALID_HEATING_CONFIGURATION",
            "Heating configuration contains an invalid value.",
        ) from error

    if (
        not token.strip()
        or not secret.strip()
        or maximum_age_seconds < 0
        or not zones
    ):
        raise HeatingApplicationConfigurationError(
            "INVALID_HEATING_CONFIGURATION",
            "Heating credentials and maximum reading age must be valid.",
        )

    return HeatingApplicationConfig(
        switchbot_token=token,
        switchbot_secret=secret,
        maximum_reading_age=timedelta(seconds=maximum_age_seconds),
        zones=zones,
    )


def run_switchbot_heating_zone(
    application_config: HeatingApplicationConfig,
    zone: HeatingZone,
    current_datetime: datetime,
    dry_run: bool = True,
    nonce_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
) -> HeatingOrchestrationResult:
    if current_datetime.tzinfo is None:
        raise HeatingApplicationConfigurationError(
            "INVALID_CURRENT_DATETIME",
            "Current datetime must include timezone information.",
        )

    heating_config = zone.configuration
    timestamp_ms = int(current_datetime.timestamp() * 1000)
    retrieved_at = current_datetime.astimezone(timezone.utc).isoformat()

    try:
        environment_data = get_switchbot_indoor_environment(
            token=application_config.switchbot_token,
            secret=application_config.switchbot_secret,
            device_id=heating_config.meter_id,
            timestamp_ms=timestamp_ms,
            nonce=nonce_factory(),
            retrieved_at=retrieved_at,
        )
        meter_reading = to_meter_reading(
            environment_data=environment_data,
            expected_meter_id=heating_config.meter_id,
            current_datetime=current_datetime,
            maximum_age=application_config.maximum_reading_age,
        )
    except IndoorEnvironmentError as error:
        meter_reading = meter_reading_from_client_error(
            error=error,
            expected_meter_id=heating_config.meter_id,
        )

    def status_provider(device_id, channel):
        return get_relay_channel_status(
            token=application_config.switchbot_token,
            secret=application_config.switchbot_secret,
            device_id=device_id,
            channel=channel,
            timestamp_ms=timestamp_ms,
            nonce=nonce_factory(),
        )

    def state_setter(device_id, channel, state):
        return set_relay_channel_state(
            token=application_config.switchbot_token,
            secret=application_config.switchbot_secret,
            device_id=device_id,
            channel=channel,
            state=state,
            timestamp_ms=timestamp_ms,
            nonce=nonce_factory(),
        )

    return run_heating_control(
        configuration=heating_config,
        readings=[meter_reading],
        status_provider=status_provider,
        state_setter=state_setter,
        dry_run=dry_run,
    )


def _load_zone(environ: Mapping[str, str], index: int) -> HeatingZone:
    prefix = f"HEATING_ZONE_{index}"
    return HeatingZone(
        name=environ[f"{prefix}_NAME"],
        configuration=HeatingConfiguration(
            relay_id=environ[f"{prefix}_RELAY_ID"],
            channel=int(environ[f"{prefix}_CHANNEL"]),
            meter_id=environ[f"{prefix}_METER_ID"],
            target_temperature=float(environ[f"{prefix}_TARGET_TEMPERATURE"]),
            hysteresis=float(environ[f"{prefix}_HYSTERESIS"]),
        ),
    )


def _zone_is_enabled(environ: Mapping[str, str], index: int) -> bool:
    key = f"HEATING_ZONE_{index}_ENABLED"
    value = environ.get(key, "false").strip().lower()
    if value not in {"true", "false"}:
        raise HeatingApplicationConfigurationError(
            "INVALID_HEATING_CONFIGURATION",
            f"{key} must be true or false.",
        )
    return value == "true"
