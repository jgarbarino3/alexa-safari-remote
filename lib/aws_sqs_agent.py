#!/usr/bin/env python3
"""Poll an AWS SQS queue and dispatch Alexa bridge actions locally."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_WAIT_SECONDS = 20
DEFAULT_VISIBILITY_SECONDS = 120


class AgentError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_dir() -> Path:
    return Path(os.environ.get("ALEXA_SAFARI_REMOTE_STATE_DIR", "~/.local/state/alexa-safari-remote")).expanduser()


def log_path() -> Path:
    return Path(os.environ.get("ALEXA_SQS_AGENT_LOG", str(state_dir() / "aws-sqs-agent.log"))).expanduser()


def append_log(event: str, **fields: Any) -> None:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_fields = " ".join(f"{key}={json.dumps(value, ensure_ascii=True)}" for key, value in fields.items())
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{utc_now()} event={event}")
        if safe_fields:
            handle.write(f" {safe_fields}")
        handle.write("\n")


def queue_url_from_env() -> str:
    value = os.environ.get("ALEXA_SQS_QUEUE_URL", "").strip()
    if not value:
        raise AgentError("ALEXA_SQS_QUEUE_URL is required.")
    return value


def aws_bin() -> str:
    return os.environ.get("AWS_BIN", "aws")


def dispatch_bin() -> str:
    return os.environ.get("ALEXA_BRIDGE_DISPATCH_BIN", "alexa-bridge-dispatch")


def run_json(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode != 0:
        raise AgentError(completed.stderr.strip() or completed.stdout.strip() or f"Command failed: {command[0]}")
    if not completed.stdout.strip():
        return {}
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AgentError(f"Invalid JSON from {command[0]}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AgentError(f"Expected JSON object from {command[0]}")
    return parsed


def receive_messages(queue_url: str, wait_seconds: int, visibility_seconds: int) -> list[dict[str, Any]]:
    payload = run_json(
        [
            aws_bin(),
            "sqs",
            "receive-message",
            "--queue-url",
            queue_url,
            "--max-number-of-messages",
            "1",
            "--wait-time-seconds",
            str(wait_seconds),
            "--visibility-timeout",
            str(visibility_seconds),
            "--output",
            "json",
        ]
    )
    messages = payload.get("Messages") or []
    if not isinstance(messages, list):
        raise AgentError("AWS receive-message returned invalid Messages.")
    return messages


def delete_message(queue_url: str, receipt_handle: str) -> None:
    subprocess.run(
        [
            aws_bin(),
            "sqs",
            "delete-message",
            "--queue-url",
            queue_url,
            "--receipt-handle",
            receipt_handle,
        ],
        check=True,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def parse_body(message: dict[str, Any]) -> dict[str, Any]:
    raw_body = message.get("Body")
    if not isinstance(raw_body, str):
        raise AgentError("SQS message is missing Body.")
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise AgentError(f"SQS body is not JSON: {exc}") from exc

    # Some relays wrap the real action in a body/message field.
    if isinstance(parsed, dict) and isinstance(parsed.get("body"), str):
        return json.loads(parsed["body"])
    if isinstance(parsed, dict) and isinstance(parsed.get("Message"), str):
        return json.loads(parsed["Message"])
    if isinstance(parsed, dict):
        return parsed
    raise AgentError("SQS body must decode to a JSON object.")


def dispatch_action(action: dict[str, Any]) -> int:
    completed = subprocess.run(
        [dispatch_bin()],
        input=json.dumps(action),
        text=True,
    )
    return completed.returncode


def handle_message(queue_url: str, message: dict[str, Any], delete_failed: bool) -> int:
    receipt_handle = message.get("ReceiptHandle")
    message_id = message.get("MessageId", "unknown")
    if not isinstance(receipt_handle, str) or not receipt_handle:
        raise AgentError("SQS message is missing ReceiptHandle.")

    try:
        action = parse_body(message)
        action_name = str(action.get("action", "unknown"))
        append_log("message_received", message_id=message_id, action=action_name)
        returncode = dispatch_action(action)
        append_log("message_dispatched", message_id=message_id, action=action_name, returncode=returncode)
        if returncode == 0 or delete_failed:
            delete_message(queue_url, receipt_handle)
            append_log("message_deleted", message_id=message_id, action=action_name, failed=returncode != 0)
        return returncode
    except Exception as exc:
        append_log("message_failed", message_id=message_id, error=str(exc))
        if delete_failed:
            delete_message(queue_url, receipt_handle)
            append_log("message_deleted", message_id=message_id, failed=True)
        return 1


def run_once(args: argparse.Namespace) -> int:
    queue_url = args.queue_url or queue_url_from_env()
    messages = receive_messages(queue_url, args.wait_seconds, args.visibility_seconds)
    if not messages:
        append_log("poll_empty")
        return 0
    return handle_message(queue_url, messages[0], args.delete_failed)


def run_forever(args: argparse.Namespace) -> int:
    queue_url = args.queue_url or queue_url_from_env()
    append_log("agent_started")
    while True:
        try:
            messages = receive_messages(queue_url, args.wait_seconds, args.visibility_seconds)
            if not messages:
                append_log("poll_empty")
            for message in messages:
                handle_message(queue_url, message, args.delete_failed)
        except AgentError as exc:
            append_log("agent_error", error=str(exc))
            time.sleep(args.error_sleep_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Poll SQS and dispatch Alexa bridge actions.")
    parser.add_argument("--queue-url", help="SQS queue URL. Defaults to ALEXA_SQS_QUEUE_URL.")
    parser.add_argument("--wait-seconds", type=int, default=DEFAULT_WAIT_SECONDS)
    parser.add_argument("--visibility-seconds", type=int, default=DEFAULT_VISIBILITY_SECONDS)
    parser.add_argument("--error-sleep-seconds", type=int, default=10)
    parser.add_argument(
        "--keep-failed",
        dest="delete_failed",
        action="store_false",
        help="Leave failed messages in SQS. Default deletes failed messages to avoid poison loops.",
    )
    parser.add_argument("--once", action="store_true", help="Poll one message and exit.")
    parser.set_defaults(delete_failed=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_once(args) if args.once else run_forever(args)
    except AgentError as exc:
        print(f"ERROR:{exc}", file=sys.stderr)
        return 2
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
