"""Operational wiring for room ventilation and humidifier control."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, time, timezone
import uuid

from smart_home_qa_harness.humidifier_control import (
    HumidifierControlResult,
    run_humidifier_control,
)
from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentData,
    IndoorEnvironmentError,
    get_switchbot_indoor_environment,
)
from smart_home_qa_harness.room_config import (
    HomeRoomConfig,
    load_room_config,
)
from smart_home_qa_harness.room_ventilation_control import (
    HomeVentilationResult,
    evaluate_home_ventilation,
)
from smart_home_qa_harness.switchbot_plug_client import (
    get_plug_status,
    set_plug_state,
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

    if (
        not token.strip()
        or not secret.strip()
        or not 0 <= humidifier_on_below < humidifier_off_at <= 100
    ):
        raise RoomControlApplicationError(
            "INVALID_ROOM_CONTROL_CONFIGURATION",
            "Credentials and humidity thresholds must be valid.",
        )

    return RoomControlApplicationConfig(
        latitude=latitude,
        longitude=longitude,
        switchbot_token=token,
        switchbot_secret=secret,
        home=home,
        humidifier_on_below=humidifier_on_below,
        humidifier_off_at=humidifier_off_at,
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
    plug_status_provider: Callable = get_plug_status,
    plug_state_setter: Callable = set_plug_state,
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
            status_provider=lambda device_id: plug_status_provider(
                token=config.switchbot_token,
                secret=config.switchbot_secret,
                device_id=device_id,
                timestamp_ms=timestamp_ms,
                nonce=nonce_factory(),
            ),
            state_setter=lambda device_id, state: plug_state_setter(
                token=config.switchbot_token,
                secret=config.switchbot_secret,
                device_id=device_id,
                state=state,
                timestamp_ms=timestamp_ms,
                nonce=nonce_factory(),
            ),
            dry_run=not apply_humidifier_commands,
            on_below=config.humidifier_on_below,
            off_at=config.humidifier_off_at,
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
