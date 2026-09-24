"""Run one non-interactive production heating cycle for a guarded pilot zone."""

from datetime import datetime
import json
import os
from zoneinfo import ZoneInfo

from smart_home_qa_harness.heating_application import (
    HeatingApplicationConfigurationError,
    load_heating_application_config,
    run_switchbot_heating_zone,
)


def main(environ=None, now_factory=None) -> int:
    environ = os.environ if environ is None else environ
    now_factory = (
        (lambda: datetime.now(ZoneInfo("Europe/Berlin")))
        if now_factory is None
        else now_factory
    )

    try:
        config = load_heating_application_config(environ)
    except HeatingApplicationConfigurationError as error:
        print(json.dumps({"event": "configuration_error", "code": error.code}))
        return 1

    scheduled_zone = environ.get("HEATING_SCHEDULED_ZONE", "")
    real_commands_allowed = (
        environ.get("ALLOW_REAL_HEATING_COMMANDS", "").lower() == "true"
    )
    if (
        len(config.zones) != 1
        or config.zones[0].name != scheduled_zone
        or scheduled_zone != "children-room"
        or not real_commands_allowed
    ):
        print(
            json.dumps(
                {
                    "event": "pilot_guard_blocked",
                    "enabled_zones": [zone.name for zone in config.zones],
                    "scheduled_zone": scheduled_zone,
                }
            )
        )
        return 1

    zone = config.zones[0]
    current_datetime = now_factory()
    result = run_switchbot_heating_zone(
        application_config=config,
        zone=zone,
        current_datetime=current_datetime,
        dry_run=False,
    )
    print(
        json.dumps(
            {
                "event": "heating_cycle",
                "timestamp": current_datetime.isoformat(),
                "zone": zone.name,
                "relay_id": result.relay_id,
                "channel": result.channel,
                "meter_id": result.meter_id,
                "previous_state": getattr(result.previous_state, "value", None),
                "desired_state": getattr(result.desired_state, "value", None),
                "command_sent": result.command_sent,
                "state_confirmed": result.state_confirmed,
                "error_code": result.error_code,
            },
            sort_keys=True,
        )
    )
    return 1 if result.error_code else 0


if __name__ == "__main__":
    raise SystemExit(main())
