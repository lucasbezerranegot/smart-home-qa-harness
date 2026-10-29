"""Run one non-interactive room ventilation and humidifier cycle."""

from datetime import datetime
import json
import os
from zoneinfo import ZoneInfo

from smart_home_qa_harness.operational_events import (
    build_operational_event,
    load_operational_alert_tracker,
)
from smart_home_qa_harness.ntfy_notifier import load_ntfy_notifier
from smart_home_qa_harness.operational_notifications import (
    deliver_operational_notification,
)
from smart_home_qa_harness.room_control_application import (
    RoomControlApplicationError,
    load_room_control_config,
    run_room_control_cycle,
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
        config = load_room_control_config(environ)
    except RoomControlApplicationError as error:
        _print_event(build_operational_event(
            timestamp=current_datetime,
            subsystem="room_control",
            scope_kind="home",
            scope="home",
            decision="configuration_rejected",
            command_status="blocked",
            confirmation_status="not_applicable",
            error_code=error.code,
            alert_tracker=alert_tracker,
        ), notifier)
        return 1

    allow_commands = (
        environ.get("ALLOW_REAL_HUMIDIFIER_COMMANDS", "false")
        .strip()
        .lower()
        == "true"
    )
    result = run_room_control_cycle(
        config=config,
        current_datetime=current_datetime,
        apply_humidifier_commands=allow_commands,
    )

    reading_failures = {
        failure.room_id: failure.error_code
        for failure in result.reading_failures
    }
    for room in config.home.rooms:
        error_code = reading_failures.get(room.room_id)
        _print_event(build_operational_event(
            timestamp=current_datetime,
            subsystem="environment_reading",
            scope_kind="room",
            scope=room.room_id,
            decision=(
                "reading_failed"
                if error_code is not None
                else "reading_succeeded"
            ),
            command_status="not_applicable",
            confirmation_status="not_applicable",
            error_code=error_code,
            alert_tracker=alert_tracker,
        ), notifier)

    if result.weather_error_code is not None:
        _print_event(build_operational_event(
            timestamp=current_datetime,
            subsystem="weather",
            scope_kind="home",
            scope="home",
            decision="reading_failed",
            command_status="not_applicable",
            confirmation_status="not_applicable",
            error_code=result.weather_error_code,
            alert_tracker=alert_tracker,
        ), notifier)
    elif result.ventilation.decisions or result.ventilation.failures:
        _print_event(build_operational_event(
            timestamp=current_datetime,
            subsystem="weather",
            scope_kind="home",
            scope="home",
            decision="reading_succeeded",
            command_status="not_applicable",
            confirmation_status="not_applicable",
            error_code=None,
            alert_tracker=alert_tracker,
        ), notifier)

    for decision in result.ventilation.decisions:
        _print_event(build_operational_event(
            timestamp=current_datetime,
            subsystem="ventilation",
            scope_kind="room",
            scope=decision.room.room_id,
            decision=decision.action.value,
            command_status="not_required",
            confirmation_status="not_applicable",
            error_code=None,
            alert_tracker=alert_tracker,
            measurements={
                "temperature_celsius": decision.temperature,
                "relative_humidity_percent": decision.relative_humidity,
            },
            state={"reason": decision.reason.value},
        ), notifier)
    for failure in result.ventilation.failures:
        _print_event(build_operational_event(
            timestamp=current_datetime,
            subsystem="ventilation",
            scope_kind="room",
            scope=failure.room_id,
            decision="unavailable",
            command_status="not_required",
            confirmation_status="not_applicable",
            error_code=failure.error_code,
            alert_tracker=alert_tracker,
        ), notifier)

    for item in result.humidifiers:
        _print_event(build_operational_event(
            timestamp=current_datetime,
            subsystem="humidifier",
            scope_kind="room",
            scope=item.room_id,
            decision=_enum_value(item.desired_state, "unavailable"),
            command_status=_humidifier_command_status(item),
            confirmation_status=(
                "confirmed" if item.state_confirmed else "unconfirmed"
            ),
            error_code=item.error_code,
            alert_tracker=alert_tracker,
            measurements={
                "relative_humidity_percent": item.relative_humidity,
            },
            state={
                "previous": _enum_value(item.previous_state),
                "reported": _enum_value(item.reported_state),
                "dry_run": item.dry_run,
            },
        ), notifier)

    cycle_failed = _has_error(result)
    _print_event(build_operational_event(
        timestamp=current_datetime,
        subsystem="room_control",
        scope_kind="home",
        scope="home",
        decision=("completed_with_errors" if cycle_failed else "completed"),
        command_status="not_applicable",
        confirmation_status="not_applicable",
        error_code=None,
        alert_tracker=alert_tracker,
    ), notifier)
    return 1 if cycle_failed else 0


def _humidifier_command_status(item) -> str:
    if item.dry_run and item.desired_state is not item.reported_state:
        return "dry_run"
    if not item.command_attempted:
        return "not_required" if item.error_code is None else "blocked"
    return "succeeded" if item.command_succeeded else "failed"


def _enum_value(value, fallback=None):
    return getattr(value, "value", fallback)


def _has_error(result) -> bool:
    return bool(
        result.weather_error_code
        or result.reading_failures
        or result.ventilation.failures
        or any(item.error_code for item in result.humidifiers)
    )


def _print_event(event, notifier) -> None:
    delivered_event = deliver_operational_notification(event, notifier)
    print(json.dumps(delivered_event, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
