"""Command-driven control client for Glial shared sessions."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from typing import Any, TextIO

from glial_net import HttpGlialClient


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="glial-control")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("GLIAL_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--user-id",
        default=os.environ.get("GLIAL_USER_ID", "demo-user"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-sessions")

    show = subparsers.add_parser("show-session")
    show.add_argument("session_id")

    contexts = subparsers.add_parser("list-contexts")
    contexts.add_argument("session_id")

    taps = subparsers.add_parser("list-taps")
    taps.add_argument("session_id")

    request_primary = subparsers.add_parser("request-primary")
    request_primary.add_argument("session_id")
    request_primary.add_argument("tap_id")
    request_primary.add_argument("--replica-id", default="headless-control")
    request_primary.add_argument("--priority", type=int, default=100)

    release_primary = subparsers.add_parser("release-primary")
    release_primary.add_argument("session_id")
    release_primary.add_argument("tap_id")
    release_primary.add_argument("--replica-id", default="headless-control")

    set_value = subparsers.add_parser("set-value")
    set_value.add_argument("session_id")
    set_value.add_argument("path")
    set_value.add_argument("grip_id")
    set_value.add_argument("json_value")

    return parser


def _json_dump(value: Any, stream: TextIO) -> None:
    json.dump(value, stream, indent=2, sort_keys=True)
    stream.write("\n")


def run_cli(
    argv: list[str],
    *,
    stdout: TextIO | None = None,
    client: HttpGlialClient | None = None,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    output = stdout or sys.stdout
    owned_client = client is None
    api = client or HttpGlialClient(base_url=args.base_url)
    try:
        if args.command == "list-sessions":
            _json_dump(api.list_remote_sessions(args.user_id), output)
            return 0

        if args.command == "show-session":
            _json_dump(api.load_shared_session(args.user_id, args.session_id), output)
            return 0

        if args.command == "list-contexts":
            _json_dump(api.list_shared_contexts(args.user_id, args.session_id), output)
            return 0

        if args.command == "list-taps":
            _json_dump(api.list_shared_taps(args.user_id, args.session_id), output)
            return 0

        if args.command == "request-primary":
            _json_dump(
                api.request_tap_lease(
                    args.user_id,
                    args.session_id,
                    args.tap_id,
                    replica_id=args.replica_id,
                    priority=args.priority,
                ),
                output,
            )
            return 0

        if args.command == "release-primary":
            api.release_tap_lease(
                args.user_id,
                args.session_id,
                args.tap_id,
                replica_id=args.replica_id,
            )
            output.write("released\n")
            return 0

        if args.command == "set-value":
            value = json.loads(args.json_value)
            _json_dump(
                api.update_shared_value(
                    args.user_id,
                    args.session_id,
                    path=args.path,
                    grip_id=args.grip_id,
                    value=value,
                ),
                output,
            )
            return 0

        parser.error(f"unknown command: {args.command}")
        return 2
    finally:
        if owned_client:
            api.close()


def main(argv: list[str] | None = None) -> int:
    return run_cli(list(argv) if argv is not None else sys.argv[1:])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
