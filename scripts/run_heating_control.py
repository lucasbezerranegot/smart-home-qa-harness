"""Run one SwitchBot heating zone safely; dry-run is the default."""

import argparse
from datetime import datetime
import os
from zoneinfo import ZoneInfo

from smart_home_qa_harness.heating_application import (
    HeatingApplicationConfigurationError,
    load_heating_application_config,
    run_switchbot_heating_zone,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zone", required=True, help="Exact configured zone name")
    parser.add_argument("--apply", action="store_true", help="Allow a real command")
    args = parser.parse_args()

    try:
        config = load_heating_application_config(os.environ)
    except HeatingApplicationConfigurationError as error:
        print(f"Configuration error: {error.code} - {error.message}")
        return 1

    zone = next((item for item in config.zones if item.name == args.zone), None)
    if zone is None:
        print(f"Unknown zone: {args.zone}")
        return 1

    dry_run = True
    if args.apply:
        if os.environ.get("ALLOW_REAL_HEATING_COMMANDS", "").lower() != "true":
            print("Real command blocked: ALLOW_REAL_HEATING_COMMANDS is not true.")
            return 1
        expected = f"APPLY {zone.name}"
        if input(f'Type "{expected}" to continue: ') != expected:
            print("Command cancelled.")
            return 1
        dry_run = False

    result = run_switchbot_heating_zone(
        application_config=config,
        zone=zone,
        current_datetime=datetime.now(ZoneInfo("Europe/Berlin")),
        dry_run=dry_run,
    )

    print(f"Zone: {zone.name}")
    print(f"Relay: {result.relay_id}, channel: {result.channel}")
    print(f"Meter: {result.meter_id}")
    print(f"Previous state: {getattr(result.previous_state, 'value', None)}")
    print(f"Desired state: {getattr(result.desired_state, 'value', None)}")
    print(f"Dry run: {result.dry_run}")
    print(f"Command sent: {result.command_sent}")
    print(f"State confirmed: {result.state_confirmed}")
    print(f"Error: {result.error_code}")
    return 1 if result.error_code else 0


if __name__ == "__main__":
    raise SystemExit(main())
