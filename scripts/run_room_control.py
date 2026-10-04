"""Run one non-interactive room ventilation and humidifier cycle."""

from dataclasses import asdict
from datetime import datetime
import json
import os
from zoneinfo import ZoneInfo

from smart_home_qa_harness.room_control_application import (
    RoomControlApplicationError,
    load_room_control_config,
    run_room_control_cycle,
)


def main() -> int:
    try:
        config = load_room_control_config(os.environ)
    except RoomControlApplicationError as error:
        print(json.dumps({"error": error.code, "message": error.message}))
        return 1

    allow_commands = (
        os.environ.get("ALLOW_REAL_HUMIDIFIER_COMMANDS", "false")
        .strip()
        .lower()
        == "true"
    )
    result = run_room_control_cycle(
        config=config,
        current_datetime=datetime.now(ZoneInfo("Europe/Berlin")),
        apply_humidifier_commands=allow_commands,
    )

    payload = asdict(result)
    print(json.dumps(payload, default=_json_default, ensure_ascii=False))
    return 1 if _has_error(result) else 0


def _has_error(result) -> bool:
    return bool(
        result.weather_error_code
        or result.reading_failures
        or any(item.error_code for item in result.humidifiers)
    )


def _json_default(value):
    return getattr(value, "value", str(value))


if __name__ == "__main__":
    raise SystemExit(main())
