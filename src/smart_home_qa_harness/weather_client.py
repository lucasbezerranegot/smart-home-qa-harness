import requests
from dataclasses import dataclass


@dataclass(frozen=True)
class WeatherData:
    outside_temperature: float
    timestamp: str


class WeatherClientError(Exception):
    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


# Configuration
BASE_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 3

def get_hourly_forecast(latitude, longitude) -> WeatherData:
    "Return the first hourly weather observation for the supplied coordinates."
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m"
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()

    except requests.exceptions.HTTPError as error:
        # A response arrived, but its status was 4xx/5xx
        raise WeatherClientError(
            code="HTTP_ERROR",
            message=f"Failed to fetch weather data: {response.status_code} - {response.text}",
            retryable=True,
        ) from error
    except requests.exceptions.Timeout as error:
        # No usable HTTP response arrived
        raise WeatherClientError(
            code="TIMEOUT",
            message="Request to weather API timed out",
            retryable=True,
        ) from error
    except requests.exceptions.JSONDecodeError as error:
        # The response was not valid JSON
        raise WeatherClientError(
            code="INVALID_JSON",
            message="Failed to decode JSON response from weather API",
            retryable=False,
        ) from error

    try:
        # Extract the first hourly observation from the payload. In the future, we may want to get the actual current hour, but for now, we just take the first one.
        temperature = payload["hourly"]["temperature_2m"][0]
        timestamp = payload["hourly"]["time"][0]
    except (KeyError, IndexError, TypeError) as error:
        raise WeatherClientError(
            code="INVALID_PAYLOAD",
            message="Weather API payload has an invalid structure.",
            retryable=False,
        ) from error

    if isinstance(temperature, bool) or not isinstance(temperature, (float, int)):
        raise WeatherClientError(
            code="INVALID_PAYLOAD",
            message="Invalid temperature value received.",
            retryable=False,
        )

    if not isinstance(timestamp, str) or not timestamp:
        raise WeatherClientError(
            code="INVALID_PAYLOAD",
            message="Invalid timestamp value received.",
            retryable=False,
        )

    return WeatherData(
        outside_temperature=temperature,
        timestamp=timestamp,
    )
