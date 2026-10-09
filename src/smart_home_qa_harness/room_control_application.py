"""Operational wiring for room ventilation and humidifier control."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, time, timezone
import math
import uuid

from smart_home_qa_harness.humidifier_control import (
    HumidifierControlResult,
    run_humidifier_control,
)
from smart_home_qa_harness.humidifier_provider import (
    HumidifierProvider,
)
from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentData,
    IndoorEnvironmentError,
    get_switchbot_indoor_environment,
)
from smart_home_qa_harness.room_config import (
    HomeRoomConfig,
    HumidifierProviderKind,
    RoomConfig,
    load_room_config,
)
from smart_home_qa_harness.room_ventilation_control import (
    HomeVentilationResult,
    evaluate_home_ventilation,
)
from smart_home_qa_harness.switchbot_humidifier_provider import (
    SwitchBotPlugHumidifierProvider,
)
from smart_home_qa_harness.vesync_humidifier_provider import (
    VeSyncHumidifierProvider,
)
from smart_home_qa_harness.weather_client import (
    WeatherClientError,
    WeatherData,
    get_current_weather,
)


@dataclass(frozen=True)
class RoomControlApplicationConfig:
    latitude: float
    longitude: float
    switchbot_token: str
    switchbot_secret: str
    home: HomeRoomConfig
    humidifier_on_below: float
    humidifier_off_at: float
    humidifier_confirmation_retry_delays_seconds: tuple[float, ...]
    vesync_username: str | None
    vesync_password: str | None
    vesync_country_code: str | None
    vesync_time_zone: str | None
    vesync_timeout_seconds: float | None


@dataclass(frozen=True)
class RoomReadingFailure:
    room_id: str
    error_code: str


@dataclass(frozen=True)
class RoomControlCycleResult:
    ventilation: HomeVentilationResult
    humidifiers: tuple[HumidifierControlResult, ...]
    reading_failures: tuple[RoomReadingFailure, ...]
    weather_error_code: str | None = None


class RoomControlApplicationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = False


def load_room_control_config(
    environ: Mapping[str, str],
) -> RoomControlApplicationConfig:
    try:
        latitude = float(environ["WEATHER_LATITUDE"])
        longitude = float(environ["WEATHER_LONGITUDE"])
        token = environ["SWITCHBOT_TOKEN"]
        secret = environ["SWITCHBOT_SECRET"]
        humidifier_on_below = float(
            environ.get("HUMIDIFIER_ON_BELOW", "45")
        )
        humidifier_off_at = float(
            environ.get("HUMIDIFIER_OFF_AT", "50")
        )
        confirmation_retry_delays_raw = environ[
            "HUMIDIFIER_CONFIRMATION_RETRY_DELAYS_SECONDS"
        ]
        home = load_room_config(environ)
    except KeyError as error:
        raise RoomControlApplicationError(
            "MISSING_ROOM_CONTROL_CONFIGURATION",
            f"Missing required configuration: {error.args[0]}",
        ) from error
    except (TypeError, ValueError) as error:
        raise RoomControlApplicationError(
            "INVALID_ROOM_CONTROL_CONFIGURATION",
            "Room control configuration contains an invalid value.",
        ) from error

    humidifier_confirmation_retry_delays_seconds = (
        _parse_confirmation_retry_delays(confirmation_retry_delays_raw)
    )

    if (
        not token.strip()
        or not secret.strip()
        or not 0 <= humidifier_on_below < humidifier_off_at <= 100
    ):
        raise RoomControlApplicationError(
            "INVALID_ROOM_CONTROL_CONFIGURATION",
            "Credentials and humidity thresholds must be valid.",
        )

    uses_vesync = any(
        room.humidifier_provider is HumidifierProviderKind.VESYNC
        for room in home.rooms
    )
    if uses_vesync:
        vesync_username = _optional_value(environ, "VESYNC_USERNAME")
        vesync_password = _optional_value(environ, "VESYNC_PASSWORD")
        vesync_country_code = _optional_value(
            environ,
            "VESYNC_COUNTRY_CODE",
        )
        vesync_time_zone = _optional_value(environ, "VESYNC_TIME_ZONE")
        vesync_timeout_raw = _optional_value(
            environ,
            "VESYNC_TIMEOUT_SECONDS",
        )
        if (
            vesync_username is None
            or vesync_password is None
            or vesync_country_code is None
            or vesync_time_zone is None
            or vesync_timeout_raw is None
        ):
            raise RoomControlApplicationError(
                "MISSING_VESYNC_CONFIGURATION",
                "All VESYNC_* settings are required for a VeSync room.",
            )
        vesync_timeout_seconds = _parse_vesync_timeout(vesync_timeout_raw)
    else:
        vesync_username = None
        vesync_password = None
        vesync_country_code = None
        vesync_time_zone = None
        vesync_timeout_seconds = None

    return RoomControlApplicationConfig(
        latitude=latitude,
        longitude=longitude,
        switchbot_token=token,
        switchbot_secret=secret,
        home=home,
        humidifier_on_below=humidifier_on_below,
        humidifier_off_at=humidifier_off_at,
        humidifier_confirmation_retry_delays_seconds=(
            humidifier_confirmation_retry_delays_seconds
        ),
        vesync_username=vesync_username,
        vesync_password=vesync_password,
        vesync_country_code=vesync_country_code,
        vesync_time_zone=vesync_time_zone,
        vesync_timeout_seconds=vesync_timeout_seconds,
    )


def run_room_control_cycle(
    config: RoomControlApplicationConfig,
    current_datetime: datetime,
    apply_humidifier_commands: bool = False,
    nonce_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    meter_reader: Callable[..., IndoorEnvironmentData] = (
        get_switchbot_indoor_environment
    ),
    weather_provider: Callable[..., WeatherData] = get_current_weather,
    humidifier_provider_factory: Callable | None = None,
) -> RoomControlCycleResult:
    """Read each Meter once and run all room-aware controllers."""

    if current_datetime.tzinfo is None:
        raise RoomControlApplicationError(
            "INVALID_CURRENT_DATETIME",
            "Current datetime must include timezone information.",
        )

    timestamp_ms = int(current_datetime.timestamp() * 1000)
    retrieved_at = current_datetime.astimezone(timezone.utc).isoformat()
    readings: dict[str, IndoorEnvironmentData] = {}
    reading_failures: list[RoomReadingFailure] = []

    for room in config.home.rooms:
        try:
            readings[room.room_id] = meter_reader(
                token=config.switchbot_token,
                secret=config.switchbot_secret,
                device_id=room.meter_id,
                timestamp_ms=timestamp_ms,
                nonce=nonce_factory(),
                retrieved_at=retrieved_at,
            )
        except IndoorEnvironmentError as error:
            reading_failures.append(
                RoomReadingFailure(room.room_id, error.code)
            )

    local_time = current_datetime.timetz().replace(tzinfo=None)
    ventilation, weather_error_code = _run_ventilation(
        config=config,
        readings=readings,
        current_time=local_time,
        weather_provider=weather_provider,
    )

    humidifier_results = tuple(
        run_humidifier_control(
            room=room,
            relative_humidity=(
                readings[room.room_id].relative_humidity
                if room.room_id in readings
                else None
            ),
            current_time=local_time,
            provider=(
                humidifier_provider_factory(room)
                if humidifier_provider_factory is not None
                else _build_humidifier_provider(
                    config=config,
                    room=room,
                    timestamp_ms=timestamp_ms,
                    nonce_factory=nonce_factory,
                )
            ),
            dry_run=not apply_humidifier_commands,
            on_below=config.humidifier_on_below,
            off_at=config.humidifier_off_at,
            confirmation_retry_delays=(
                config.humidifier_confirmation_retry_delays_seconds
            ),
        )
        for room in config.home.humidifier_rooms
    )

    return RoomControlCycleResult(
        ventilation=ventilation,
        humidifiers=humidifier_results,
        reading_failures=tuple(reading_failures),
        weather_error_code=weather_error_code,
    )


def _run_ventilation(
    config: RoomControlApplicationConfig,
    readings: dict[str, IndoorEnvironmentData],
    current_time: time,
    weather_provider: Callable[..., WeatherData],
) -> tuple[HomeVentilationResult, str | None]:
    empty_result = HomeVentilationResult((), (), ())
    if not _is_ventilation_period(current_time):
        return empty_result, None

    try:
        weather = weather_provider(
            latitude=config.latitude,
            longitude=config.longitude,
        )
    except WeatherClientError as error:
        return empty_result, error.code

    return (
        evaluate_home_ventilation(
            home=config.home,
            readings=readings,
            outside_temperature=weather.outside_temperature,
            daily_max_temperature=weather.daily_max_temperature,
            current_time=current_time,
        ),
        None,
    )


def _is_ventilation_period(current_time: time) -> bool:
    return (
        time(6, 0) <= current_time <= time(11, 0)
        or time(18, 0) <= current_time <= time(23, 0)
    )


def _build_humidifier_provider(
    config: RoomControlApplicationConfig,
    room: RoomConfig,
    timestamp_ms: int,
    nonce_factory: Callable[[], str],
) -> HumidifierProvider:
    if room.humidifier_provider is HumidifierProviderKind.SWITCHBOT_PLUG:
        return SwitchBotPlugHumidifierProvider(
            token=config.switchbot_token,
            secret=config.switchbot_secret,
            plug_device_id=room.humidifier_device_id,
            timestamp_ms=timestamp_ms,
            nonce_factory=nonce_factory,
        )
    if room.humidifier_provider is HumidifierProviderKind.VESYNC:
        assert config.vesync_username is not None
        assert config.vesync_password is not None
        assert config.vesync_country_code is not None
        assert config.vesync_time_zone is not None
        assert config.vesync_timeout_seconds is not None
        return VeSyncHumidifierProvider(
            username=config.vesync_username,
            password=config.vesync_password,
            humidifier_device_id=room.humidifier_device_id,
            country_code=config.vesync_country_code,
            time_zone=config.vesync_time_zone,
            timeout_seconds=config.vesync_timeout_seconds,
        )
    raise AssertionError("Unsupported configured humidifier provider.")


def _optional_value(
    environ: Mapping[str, str],
    key: str,
) -> str | None:
    return environ.get(key, "").strip() or None


def _parse_vesync_timeout(raw_value: str) -> float:
    try:
        timeout_seconds = float(raw_value)
    except (TypeError, ValueError) as error:
        raise RoomControlApplicationError(
            "INVALID_VESYNC_CONFIGURATION",
            "VESYNC_TIMEOUT_SECONDS must be a positive finite number.",
        ) from error
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise RoomControlApplicationError(
            "INVALID_VESYNC_CONFIGURATION",
            "VESYNC_TIMEOUT_SECONDS must be a positive finite number.",
        )
    return timeout_seconds


def _parse_confirmation_retry_delays(
    raw_value: str,
) -> tuple[float, ...]:
    try:
        delays = tuple(
            float(item.strip()) for item in raw_value.split(",")
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise RoomControlApplicationError(
            "INVALID_HUMIDIFIER_CONFIRMATION_CONFIGURATION",
            "Humidifier confirmation delays must be comma-separated numbers.",
        ) from error
    if not delays or any(
        not math.isfinite(delay) or delay <= 0 for delay in delays
    ):
        raise RoomControlApplicationError(
            "INVALID_HUMIDIFIER_CONFIRMATION_CONFIGURATION",
            "Humidifier confirmation delays must be positive finite numbers.",
        )
    return delays
