"""Run one guarded production heating cycle across scheduled zones."""

from datetime import datetime
import json
import os
from zoneinfo import ZoneInfo

from smart_home_qa_harness.heating_application import (
    HeatingApplicationConfigurationError,
    load_heating_application_config,
    load_scheduled_heating_zones,
    run_switchbot_heating_zone,
)
from smart_home_qa_harness.operational_events import (
    build_operational_event,
    load_operational_alert_tracker,
)
from smart_home_qa_harness.ntfy_notifier import load_ntfy_notifier
from smart_home_qa_harness.operational_notifications import (
    deliver_operational_notification,
)


def main(environ=None, now_factory=None) -> int:
    environ = os.environ if environ is None else environ
    now_factory = (
        (lambda: datetime.now(ZoneInfo("Europe/Berlin")))
        if now_factory is None
        else now_factory
    )
    current_datetime = now_factory()
    alert_tracker = load_operational_alert_tracker(environ)
    notifier = load_ntfy_notifier(environ)

    try:
        config = load_heating_application_config(environ)
        scheduled_zones = load_scheduled_heating_zones(config, environ)
    except HeatingApplicationConfigurationError as error:
        _print_event(build_operational_event(
            timestamp=current_datetime,
            subsystem="heating",
            scope_kind="home",
            scope="home",
            decision="configuration_rejected",
            command_status="blocked",
            confirmation_status="not_applicable",
            error_code=error.code,
            alert_tracker=alert_tracker,
        ), notifier)
        return 1

    real_commands_allowed = (
        environ.get("ALLOW_REAL_HEATING_COMMANDS", "").strip().lower()
        == "true"
    )
    if not real_commands_allowed:
        _print_event(build_operational_event(
            timestamp=current_datetime,
            subsystem="heating",
            scope_kind="home",
            scope="home",
            decision="schedule_blocked",
            command_status="blocked",
            confirmation_status="not_applicable",
            error_code="REAL_HEATING_COMMANDS_NOT_ALLOWED",
            alert_tracker=alert_tracker,
        ), notifier)
        return 1

    cycle_failed = False
    for zone in scheduled_zones:
        try:
            result = run_switchbot_heating_zone(
                application_config=config,
                zone=zone,
                current_datetime=current_datetime,
                dry_run=False,
            )
            event = build_operational_event(
                timestamp=current_datetime,
                subsystem="heating",
                scope_kind="zone",
                scope=zone.name,
                decision=getattr(result.desired_state, "value", "unavailable"),
                command_status=_heating_command_status(result),
                confirmation_status=(
                    "confirmed" if result.state_confirmed else "unconfirmed"
                ),
                error_code=result.error_code,
                alert_tracker=alert_tracker,
                state={
                    "previous": getattr(result.previous_state, "value", None),
                    "desired": getattr(result.desired_state, "value", None),
                },
            )
            cycle_failed = cycle_failed or result.error_code is not None
        except Exception:
            event = build_operational_event(
                timestamp=current_datetime,
                subsystem="heating",
                scope_kind="zone",
                scope=zone.name,
                decision="unavailable",
                command_status="unknown",
                confirmation_status="unconfirmed",
                error_code="HEATING_ZONE_EXECUTION_FAILED",
                alert_tracker=alert_tracker,
            )
            cycle_failed = True
        _print_event(event, notifier)

    _print_event(build_operational_event(
        timestamp=current_datetime,
        subsystem="heating",
        scope_kind="home",
        scope="home",
        decision=(
            "completed_with_errors" if cycle_failed else "completed"
        ),
        command_status="not_applicable",
        confirmation_status="not_applicable",
        error_code=None,
        alert_tracker=alert_tracker,
    ), notifier)
    return 1 if cycle_failed else 0


def _heating_command_status(result) -> str:
    if result.command_sent:
        return "succeeded" if result.error_code is None else "failed"
    if result.error_code is not None:
        return "blocked"
    return "not_required"


def _print_event(event, notifier) -> None:
    delivered_event = deliver_operational_notification(event, notifier)
    print(json.dumps(delivered_event, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
