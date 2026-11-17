"""Renew or control the ntfy dead-man switch."""

import argparse
from datetime import datetime, timezone
import json
import os

from smart_home_qa_harness.ntfy_heartbeat import (
    NtfyHeartbeatError,
    load_ntfy_heartbeat_config,
    run_heartbeat,
)


def main(argv=None, environ=None, now_factory=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("renew", "pause", "resume"),
        default="renew",
        nargs="?",
    )
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    now_factory = (
        (lambda: datetime.now(timezone.utc))
        if now_factory is None
        else now_factory
    )
    timestamp = now_factory()
    try:
        config = load_ntfy_heartbeat_config(environ)
        if config is None:
            _print_event("disabled", timestamp)
            return 0
        event = run_heartbeat(config, args.action, timestamp)
        print(json.dumps(event, sort_keys=True, ensure_ascii=False))
        return 0
    except NtfyHeartbeatError as error:
        _print_event("failed", timestamp, error.code, error.retryable)
        return 1
    except ValueError:
        _print_event("failed", timestamp, "NTFY_HEARTBEAT_TIME_INVALID", False)
        return 1


def _print_event(
    status,
    timestamp,
    error_code=None,
    retryable=False,
):
    print(json.dumps({
        "event": "ntfy_heartbeat",
        "status": status,
        "timestamp": timestamp.isoformat(),
        "deadline": None,
        "recovery_sent": False,
        "error_code": error_code,
        "retryable": retryable,
    }, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
