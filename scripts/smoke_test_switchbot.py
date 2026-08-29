"""Manual read-only smoke test for a real SwitchBot Meter."""

import os
import time
import uuid
from datetime import datetime, timezone

from smart_home_qa_harness.inside_environment_client import (
    get_switchbot_indoor_environment,
)


token = os.environ["SWITCHBOT_TOKEN"]
secret = os.environ["SWITCHBOT_SECRET"]
device_id = os.environ["SWITCHBOT_DEVICE_ID"]

result = get_switchbot_indoor_environment(
    token=token,
    secret=secret,
    device_id=device_id,
    timestamp_ms=int(time.time() * 1000),
    nonce=str(uuid.uuid4()),
    retrieved_at=datetime.now(timezone.utc).isoformat(),
)

print(f"Temperature: {result.temperature} °C")
print(f"Humidity: {result.relative_humidity} %")
print(f"Source: {result.source}")
print(f"Retrieved at: {result.retrieved_at}")
