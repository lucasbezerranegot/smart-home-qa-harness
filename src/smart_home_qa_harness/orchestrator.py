from dataclasses import dataclass
from datetime import date, time
from smart_home_qa_harness.decision_engine import (
    WindowAction,
    decide_window_action,
)
from collections.abc import Callable
from smart_home_qa_harness.inside_environment_client import (
    IndoorEnvironmentData,
    IndoorEnvironmentError,
)
from smart_home_qa_harness.weather_client import (
    WeatherClientError,
    get_hourly_forecast,
)
from smart_home_qa_harness.webhook_notifier import (
    WebhookError,
    send_window_action,
)

@dataclass(frozen=True)
class OrchestrationResult:
    action: WindowAction
    webhook_sent: bool
    error_code: str | None = None
    notification_suppressed: bool = False

def run_environment_control(
    latitude: float,
    longitude: float,
    inside_environment_provider: Callable[[], IndoorEnvironmentData],
    current_date: date,
    current_time: time,
    sent_notification_keys: set[str],
    api_token: str,
    open_device_id: str,
    close_device_id: str,
) -> OrchestrationResult:
    try:
        weather = get_hourly_forecast(
            latitude=latitude,
            longitude=longitude,
        )
    except WeatherClientError as error:
        return OrchestrationResult(
            action=WindowAction.NO_ACTION,
            webhook_sent=False,
            error_code=error.code,
        )

    try:
        inside_environment = inside_environment_provider()
    except IndoorEnvironmentError as error:
        return OrchestrationResult(
            action=WindowAction.NO_ACTION,
            webhook_sent=False,
            error_code=error.code,
        )

    action = decide_window_action(
        outside_temperature=weather.outside_temperature,
        inside_temperature=inside_environment.temperature,
        current_time=current_time,
    )

    notification_key = build_notification_key(
        current_date=current_date,
        action=action,
    )

    if (
        notification_key is not None
        and notification_key in sent_notification_keys
    ):
        return OrchestrationResult(
            action=action,
            webhook_sent=False,
            error_code=None,
            notification_suppressed=True,
        )

    webhook_sent = False
    if action is not WindowAction.NO_ACTION:
        try:
            send_window_action(
                api_token=api_token,
                action=action,
                open_device_id=open_device_id,
                close_device_id=close_device_id,
            )
        except WebhookError as error:
            return OrchestrationResult(
                action=action,
                webhook_sent=False,
                error_code=error.code,
            )

        webhook_sent = True
        if notification_key is not None:
            sent_notification_keys.add(notification_key)

    return OrchestrationResult(
        action=action,
        webhook_sent=webhook_sent,
        error_code=None,
    )

def build_notification_key(
    current_date: date,
    action: WindowAction,
) -> str | None:
    if action is WindowAction.NO_ACTION:
        return None

    if action is WindowAction.OPEN_WINDOWS:
        period = "evening"
    else:
        period = "morning"

    return f"{current_date.isoformat()}:{period}"
