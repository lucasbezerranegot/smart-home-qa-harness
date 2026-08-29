"""Indoor environment providers and SwitchBot API integration."""

from dataclasses import dataclass
import base64
import hashlib
import hmac
import requests

SWITCHBOT_BASE_URL = "https://api.switch-bot.com/v1.1"
SWITCHBOT_TIMEOUT_SECONDS = 3

@dataclass(frozen=True)
class IndoorEnvironmentData:
    """Normalized indoor measurements returned by any environment provider."""

    temperature: float
    relative_humidity: float | None
    retrieved_at: str
    source: str

class IndoorEnvironmentError(Exception):
    """Stable application error translated from input or provider failures."""

    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


def get_static_indoor_environment(
    temperature: float,
    retrieved_at: str,
) -> IndoorEnvironmentData:
    """Return deterministic demo data without calling an external provider."""

    if isinstance(temperature, bool) or not isinstance(
        temperature,
        (float, int),
    ):
        raise IndoorEnvironmentError(
            code="INVALID_ENVIRONMENT_INPUT",
            message="Invalid temperature value provided.",
            retryable=False,
        )

    return IndoorEnvironmentData(
        temperature=temperature,
        relative_humidity=None,
        retrieved_at=retrieved_at,
        source="static-demo",
    )

def parse_switchbot_environment(
    payload: dict,
    retrieved_at: str,
    expected_device_id: str | None = None,
) -> IndoorEnvironmentData:
    """Validate and normalize a SwitchBot device-status payload."""

    # Validate the provider envelope before reading device measurements. An HTTP
    # 200 response can still contain a SwitchBot-level failure such as code 190.
    try:
        status_code = payload["statusCode"]
    except (KeyError, TypeError) as error:
        raise IndoorEnvironmentError(
            code="SWITCHBOT_INVALID_PAYLOAD",
            message="SwitchBot payload has an invalid status code structure.",
            retryable=False,
        ) from error

    # bool is a subclass of int in Python, so it must be rejected explicitly.
    if isinstance(status_code, bool) or not isinstance(status_code, int):
        raise IndoorEnvironmentError(
            code="SWITCHBOT_INVALID_PAYLOAD",
            message="Invalid status code provided.",
            retryable=False,
        )

    provider_message = payload.get("message", "Unknown provider error")
    if status_code != 100:
        raise IndoorEnvironmentError(
            code="SWITCHBOT_API_ERROR",
            message=(
            f"SwitchBot API returned status code {status_code}: "
            f"{provider_message}"
            ),
            retryable=status_code == 190,
        )

    # Translate schema changes into our stable error contract instead of
    # leaking KeyError or TypeError to the orchestrator.
    try:
        body = payload["body"]
        temperature = body["temperature"]
        relative_humidity = body["humidity"]
        device_id = body["deviceId"]
    except (KeyError, TypeError) as error:
        raise IndoorEnvironmentError(
            code="SWITCHBOT_INVALID_PAYLOAD",
            message="SwitchBot payload has an invalid structure.",
            retryable=False,
        ) from error

    if isinstance(temperature, bool) or not isinstance(
        temperature,
        (float, int),
    ):
        raise IndoorEnvironmentError(
            code="SWITCHBOT_INVALID_PAYLOAD",
            message="Invalid temperature value provided.",
            retryable=False,
        )

    if (
    isinstance(relative_humidity, bool)
    or not isinstance(relative_humidity, (int, float))
    or not 0 <= relative_humidity <= 100
    ):
        raise IndoorEnvironmentError(
            code="SWITCHBOT_INVALID_PAYLOAD",
            message="SwitchBot returned invalid humidity.",
            retryable=False,
        )

    if not isinstance(device_id, str) or not device_id.strip():
        raise IndoorEnvironmentError(
            code="SWITCHBOT_INVALID_PAYLOAD",
            message="SwitchBot returned an invalid device ID.",
            retryable=False,
        )

    # Never let measurements from another room/device drive an automation.
    if (
        expected_device_id is not None
        and device_id != expected_device_id
    ):
        raise IndoorEnvironmentError(
            code="SWITCHBOT_DEVICE_MISMATCH",
            message="SwitchBot returned data for a different device.",
            retryable=False,
        )

    # Normalize the values to ensure they are of the correct type
    temperature = float(temperature)
    relative_humidity = float(relative_humidity)

    return IndoorEnvironmentData(
        temperature=temperature,
        relative_humidity=relative_humidity,
        retrieved_at=retrieved_at,
        source=f"switchbot:{device_id}",
    )

def build_switchbot_headers(
    token: str,
    secret: str,
    timestamp_ms: int,
    nonce: str,
) -> dict[str, str]:
    """Build deterministic HMAC-SHA256 headers for SwitchBot API v1.1."""

    # Validate before signing so programming/configuration errors fail clearly.
    if not isinstance(token, str) or not token.strip():
        raise IndoorEnvironmentError(
            code="SWITCHBOT_INVALID_CREDENTIALS",
            message="SwitchBot returned an invalid token.",
            retryable=False,
        )

    if isinstance(timestamp_ms, bool) or not isinstance(timestamp_ms, int):
        raise IndoorEnvironmentError(
            code="SWITCHBOT_INVALID_CREDENTIALS",
            message="SwitchBot timestamp must be an integer.",
            retryable=False,
        )

    if not isinstance(secret, str) or not secret.strip():
        raise IndoorEnvironmentError(
            code="SWITCHBOT_INVALID_CREDENTIALS",
            message="SwitchBot returned an invalid secret.",
            retryable=False,
        )

    if not isinstance(nonce, str) or not nonce.strip():
        raise IndoorEnvironmentError(
            code="SWITCHBOT_INVALID_CREDENTIALS",
            message="SwitchBot returned an invalid nonce.",
            retryable=False,
        )

    # SwitchBot signs token + timestamp + nonce using the account secret.
    content = f"{token}{timestamp_ms}{nonce}".encode("utf-8")
    secret_bytes = secret.encode("utf-8")

    digest = hmac.new(
        secret_bytes,
        content,
        hashlib.sha256,
    ).digest()

    signature = base64.b64encode(digest).decode("utf-8").upper()

    return {
        "Authorization": token,
        "t": str(timestamp_ms),
        "nonce": nonce,
        "Content-Type": "application/json; charset=utf8",
        "sign": signature,
    }


def get_switchbot_indoor_environment(
    token: str,
    secret: str,
    device_id: str,
    timestamp_ms: int,
    nonce: str,
    retrieved_at: str,
) -> IndoorEnvironmentData:
    """Fetch, validate, and normalize measurements from one SwitchBot device."""

    # Reject invalid identifiers before performing any external HTTP call.
    if not isinstance(device_id, str) or not device_id.strip():
        raise IndoorEnvironmentError(
            code="SWITCHBOT_INVALID_DEVICE_ID",
            message="A valid SwitchBot device ID is required.",
            retryable=False,
        )

    headers = build_switchbot_headers(
        token=token,
        secret=secret,
        timestamp_ms=timestamp_ms,
        nonce=nonce,
    )

    try:
        url = (
            f"{SWITCHBOT_BASE_URL}/devices/{device_id}/status"
        )

        response = requests.get(
            url=url,
            headers=headers,
            timeout=SWITCHBOT_TIMEOUT_SECONDS,
        )

        response.raise_for_status()

    except requests.exceptions.HTTPError as error:
        status_code = response.status_code
        # Rate limiting and server failures may succeed on a later attempt;
        # other client errors generally require configuration/input changes.
        retryable = status_code == 429 or status_code >= 500

        raise IndoorEnvironmentError(
            code="SWITCHBOT_HTTP_ERROR",
            message=f"Failed to fetch SwitchBot data: {status_code}",
            retryable=retryable,
        ) from error
    except requests.exceptions.Timeout as error:
        # Translate requests-specific exceptions so callers depend only on the
        # IndoorEnvironmentError contract.
        raise IndoorEnvironmentError(
            code="SWITCHBOT_TIMEOUT",
            message="SwitchBot API took too long to respond.",
            retryable=True
        ) from error
    except requests.exceptions.ConnectionError as error:
        raise IndoorEnvironmentError(
            code="SWITCHBOT_CONNECTION_ERROR",
            message="Could not connect to the SwitchBot API.",
            retryable=True,
        ) from error

    # HTTP success does not guarantee that the response body is valid JSON.
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError as error:
        raise IndoorEnvironmentError(
            code="SWITCHBOT_INVALID_JSON",
            message="SwitchBot API returned invalid JSON.",
            retryable=False,
        ) from error

    return parse_switchbot_environment(
        payload=payload,
        retrieved_at=retrieved_at,
        expected_device_id=device_id,
    )
