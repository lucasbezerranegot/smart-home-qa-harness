"""Application wiring and environment-based configuration.

This module connects the already isolated HTTP clients and orchestrator. It
does not read a ``.env`` file itself; deployment environments provide values
through ``os.environ`` (or another mapping supplied by the caller).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from smart_home_qa_harness.inside_environment_client import (
    get_switchbot_indoor_environment,
)
from smart_home_qa_harness.orchestrator import (
    OrchestrationResult,
    run_environment_control,
)


@dataclass(frozen=True)
class ApplicationConfig:
    """Validated configuration required for one application execution."""

    latitude: float
    longitude: float
    switchbot_token: str
    switchbot_secret: str
    switchbot_device_id: str
    voice_monkey_api_token: str
    voice_monkey_open_device_id: str
    voice_monkey_close_device_id: str

class ConfigurationError(Exception):
    """Stable configuration failure that callers can report without crashing."""

    def __init__(
        self,
        code: str,
        message: str,
        retryable: bool,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def load_application_config(
    environ: Mapping[str, str],
) -> ApplicationConfig:
    """Translate string environment variables into typed application config."""

    try:
        return ApplicationConfig(
            latitude=float(environ["WEATHER_LATITUDE"]),
            longitude=float(environ["WEATHER_LONGITUDE"]),
            switchbot_token=environ["SWITCHBOT_TOKEN"],
            switchbot_secret=environ["SWITCHBOT_SECRET"],
            switchbot_device_id=environ["SWITCHBOT_DEVICE_ID"],
            voice_monkey_api_token=environ["VOICE_MONKEY_API_TOKEN"],
            voice_monkey_open_device_id=environ["VOICE_MONKEY_OPEN_DEVICE_ID"],
            voice_monkey_close_device_id=environ["VOICE_MONKEY_CLOSE_DEVICE_ID"],
        )
    except KeyError as error:
        # KeyError stores the missing environment-variable name in args[0].
        missing_key = error.args[0]

        raise ConfigurationError(
            code="MISSING_CONFIGURATION",
            message=f"Missing required configuration: {missing_key}",
            retryable=False,
        ) from error
    except (TypeError, ValueError) as error:
        raise ConfigurationError(
            code="INVALID_CONFIGURATION",
            message="Weather coordinates must be numeric.",
            retryable=False,
        ) from error

def run_application(
    config: ApplicationConfig,
    current_datetime: datetime,
    nonce: str,
    sent_notification_keys: set[str],
) -> OrchestrationResult:
    """Wire one SwitchBot reading into one environment-control execution."""

    # The orchestrator accepts a provider function instead of SwitchBot
    # credentials. This closure adapts our concrete SwitchBot client to that
    # small interface while keeping secrets out of the orchestrator.
    def inside_environment_provider():
        return get_switchbot_indoor_environment(
            token=config.switchbot_token,
            secret=config.switchbot_secret,
            device_id=config.switchbot_device_id,
            timestamp_ms=int(current_datetime.timestamp() * 1000),
            nonce=nonce,
            retrieved_at=current_datetime.astimezone(
                timezone.utc,
            ).isoformat(),
        )

    # current_datetime is supplied by the caller so tests do not depend on the
    # real clock. The decision engine expects a timezone-free ``time`` value.
    return run_environment_control(
        latitude=config.latitude,
        longitude=config.longitude,
        inside_environment_provider=inside_environment_provider,
        current_date=current_datetime.date(),
        current_time=current_datetime.time().replace(tzinfo=None),
        sent_notification_keys=sent_notification_keys,
        api_token=config.voice_monkey_api_token,
        open_device_id=config.voice_monkey_open_device_id,
        close_device_id=config.voice_monkey_close_device_id,
    )
