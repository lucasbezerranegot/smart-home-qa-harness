import requests

from smart_home_qa_harness.decision_engine import WindowAction


WEBHOOK_TIMEOUT_SECONDS = 3
VOICE_MONKEY_TRIGGER_URL = "https://api-v3.voicemonkey.io/trigger"

class WebhookError(Exception):
    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


def send_window_action(
    api_token: str,
    action: WindowAction,
    open_device_id: str,
    close_device_id: str,
) -> None:

    if not isinstance(action, WindowAction):
        raise WebhookError(
            code="INVALID_WEBHOOK_INPUT",
            message="Action is invalid or not a WindowAction",
            retryable=False
        )

    if action is WindowAction.NO_ACTION:
        return

    if action is WindowAction.OPEN_WINDOWS:
        selected_device_id = open_device_id
    else:
        selected_device_id = close_device_id

    if not isinstance(api_token, str) or not api_token.strip():
        raise WebhookError(
            code="INVALID_WEBHOOK_INPUT",
            message="API token is invalid or empty",
            retryable=False
        )

    if not isinstance(selected_device_id, str) or not selected_device_id.strip():
        raise WebhookError(
                code="INVALID_WEBHOOK_INPUT",
                message="Selected device ID is invalid or empty",
                retryable=False
        )

    payload = {
        "token": api_token,
        "device": selected_device_id,
    }

    try:
        response = requests.post(
            VOICE_MONKEY_TRIGGER_URL,
            json=payload,
            timeout=WEBHOOK_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout as error:
        raise WebhookError(
            code="WEBHOOK_TIMEOUT",
            message="Webhook took too long to respond",
            retryable=True,
        ) from error

    except requests.exceptions.HTTPError as error:
        if error.response.status_code >= 500 or error.response.status_code == 429:
            raise WebhookError(
                code="WEBHOOK_HTTP_ERROR",
                message=f"Webhook returned an HTTP error: {error.response.status_code}",
                retryable=True,
            ) from error
        else:
            raise WebhookError(
                code="WEBHOOK_HTTP_ERROR",
                message=f"Webhook returned an HTTP error: {error.response.status_code}",
                retryable=False,
            ) from error
