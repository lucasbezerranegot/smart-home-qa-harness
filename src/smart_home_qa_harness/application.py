from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ApplicationConfig:
    latitude: float
    longitude: float
    switchbot_token: str
    switchbot_secret: str
    switchbot_device_id: str
    voice_monkey_api_token: str
    voice_monkey_open_device_id: str
    voice_monkey_close_device_id: str

class ConfigurationError(Exception):
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
