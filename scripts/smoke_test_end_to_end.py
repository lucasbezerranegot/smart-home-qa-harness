"""Manual end-to-end smoke test with an optional real Alexa trigger."""

import os
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from smart_home_qa_harness.application import load_application_config
from smart_home_qa_harness.decision_engine import (
    WindowAction,
    decide_window_action,
)
from smart_home_qa_harness.inside_environment_client import (
    get_switchbot_indoor_environment,
)
from smart_home_qa_harness.weather_client import get_current_weather
from smart_home_qa_harness.webhook_notifier import send_window_action


config = load_application_config(os.environ)
local_now = datetime.now(ZoneInfo("Europe/Berlin"))

weather = get_current_weather(
    latitude=config.latitude,
    longitude=config.longitude,
)

inside = get_switchbot_indoor_environment(
    token=config.switchbot_token,
    secret=config.switchbot_secret,
    device_id=config.switchbot_device_id,
    timestamp_ms=int(time.time() * 1000),
    nonce=str(uuid.uuid4()),
    retrieved_at=datetime.now(timezone.utc).isoformat(),
)

action = decide_window_action(
    outside_temperature=weather.outside_temperature,
    inside_temperature=inside.temperature,
    current_time=local_now.time().replace(tzinfo=None),
)

print(f"Local time: {local_now.isoformat()}")
print(f"Outside temperature: {weather.outside_temperature} °C")
print(f"Weather timestamp: {weather.timestamp}")
print(f"Inside temperature: {inside.temperature} °C")
print(f"Inside humidity: {inside.relative_humidity} %")
print(f"Decision: {action.value}")

forced_action_value = os.environ.get("SMOKE_FORCE_ACTION")

if forced_action_value:
    try:
        forced_action = WindowAction(forced_action_value)
    except ValueError as error:
        valid_actions = (
            WindowAction.OPEN_WINDOWS.value,
            WindowAction.CLOSE_WINDOWS.value,
        )
        raise SystemExit(
            f"Invalid SMOKE_FORCE_ACTION. Use one of: {valid_actions}"
        ) from error

    if forced_action is WindowAction.NO_ACTION:
        raise SystemExit(
            "SMOKE_FORCE_ACTION cannot be NO_ACTION."
        )

    print(
        "WARNING: overriding the real decision "
        f"{action.value} with {forced_action.value}."
    )
    action = forced_action

if action is WindowAction.NO_ACTION:
    print("No trigger sent because the decision was NO_ACTION.")
    raise SystemExit(0)

trigger_allowed = (
    os.environ.get("ALLOW_REAL_ALEXA_TRIGGER", "").lower() == "true"
)

if not trigger_allowed:
    print(
        "Trigger blocked. Set ALLOW_REAL_ALEXA_TRIGGER=true "
        "to enable a real Alexa notification."
    )
    raise SystemExit(0)

expected_confirmation = f"TRIGGER {action.value}"

confirmation = input(
    "This will trigger Alexa and a phone notification. "
    f"Type {expected_confirmation} to continue: "
)

if confirmation != expected_confirmation:
    print("Trigger cancelled.")
    raise SystemExit(0)

send_window_action(
    api_token=config.voice_monkey_api_token,
    action=action,
    open_device_id=config.voice_monkey_open_device_id,
    close_device_id=config.voice_monkey_close_device_id,
)

print("Voice Monkey trigger sent successfully.")
