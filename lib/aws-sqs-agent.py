#!/usr/bin/env python3
"""Long-poll an SQS queue and run safari-remote commands."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_CONFIG = Path.home() / ".config" / "alexa-safari-remote" / "aws-bridge.env"
DEFAULT_LOG = Path.home() / ".local" / "state" / "alexa-safari-remote" / "aws-sqs-agent.log"
DEFAULT_SAFARI_REMOTE = Path.home() / ".local" / "bin" / "safari-remote"


class AgentError(Exception):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll SQS for Alexa Safari Remote commands.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to aws-bridge.env")
    parser.add_argument("--once", action="store_true", help="Process at most one message, then exit")
    parser.add_argument("--print-command", help="Print mapped argv for a message JSON body, then exit")
    args = parser.parse_args()

    if args.print_command:
        argv = command_for_message(json.loads(args.print_command), DEFAULT_SAFARI_REMOTE)
        print(json.dumps([str(item) for item in argv]))
        return 0

    config = read_env_file(Path(args.config))
    agent = SqsAgent(config)
    return agent.run_once() if args.once else agent.run_forever()


class SqsAgent:
    def __init__(self, config: dict[str, str]) -> None:
        self.queue_url = required(config, "QUEUE_URL")
        self.region = config.get("AWS_REGION", "us-east-1")
        self.profile = config.get("AWS_PROFILE", "")
        self.wait_seconds = int(config.get("WAIT_TIME_SECONDS", "20"))
        self.visibility_timeout = int(config.get("VISIBILITY_TIMEOUT_SECONDS", "45"))
        self.safari_remote = Path(config.get("SAFARI_REMOTE_PATH", str(DEFAULT_SAFARI_REMOTE)))
        self.log_file = Path(config.get("AGENT_LOG_FILE", str(DEFAULT_LOG)))

    def run_forever(self) -> int:
        self.log("agent_start")
        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                self.log("agent_stop")
                return 0
            except Exception as error:
                self.log("agent_error", error=str(error))
                time.sleep(5)

    def run_once(self) -> int:
        message = self.receive_message()
        if not message:
            return 0

        message_id = str(message.get("MessageId", "unknown"))
        receipt_handle = message.get("ReceiptHandle")
        body_text = str(message.get("Body", "{}"))

        try:
            media_action = json.loads(body_text)
            argv = command_for_message(media_action, self.safari_remote)
        except Exception as error:
            self.log("invalid_message", message_id=message_id, error=str(error))
            if receipt_handle:
                self.delete_message(str(receipt_handle))
            return 2

        action_name = action_from_argv(argv)
        self.log("command_start", message_id=message_id, action=action_name)
        completed = subprocess.run(argv, text=True, capture_output=True, check=False)
        self.log(
            "command_done",
            message_id=message_id,
            action=action_name,
            returncode=str(completed.returncode),
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )

        if receipt_handle:
            self.delete_message(str(receipt_handle))
            self.log("message_deleted", message_id=message_id, action=action_name)

        return completed.returncode

    def receive_message(self) -> dict[str, object] | None:
        result = run_aws_json(self.aws_args([
            "sqs",
            "receive-message",
            "--queue-url",
            self.queue_url,
            "--max-number-of-messages",
            "1",
            "--wait-time-seconds",
            str(self.wait_seconds),
            "--visibility-timeout",
            str(self.visibility_timeout),
            "--output",
            "json",
        ]))
        messages = result.get("Messages") or []
        return messages[0] if messages else None

    def delete_message(self, receipt_handle: str) -> None:
        run_aws_json(self.aws_args([
            "sqs",
            "delete-message",
            "--queue-url",
            self.queue_url,
            "--receipt-handle",
            receipt_handle,
            "--output",
            "json",
        ]))

    def aws_args(self, args: list[str]) -> list[str]:
        command = ["aws", "--region", self.region]
        if self.profile:
            command.extend(["--profile", self.profile])
        command.extend(args)
        return command

    def log(self, event: str, **fields: str) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        parts = [timestamp, f"event={shell_word(event)}"]
        for key, value in fields.items():
            if value:
                parts.append(f"{key}={shell_word(value)}")
        with self.log_file.open("a", encoding="utf-8") as handle:
            handle.write(" ".join(parts) + "\n")


def command_for_message(message: dict[str, object], safari_remote: Path) -> list[str]:
    action = str(message.get("action", "")).strip().lower()
    if action in {"play", "pause", "toggle", "fullscreen", "escape"}:
        return [str(safari_remote), action]

    if action in {"back", "forward"}:
        seconds = positive_int(message.get("seconds"), default=10)
        return [str(safari_remote), action, str(seconds)]

    if action == "seek":
        seconds = positive_int(message.get("seconds"), default=None)
        return [str(safari_remote), "seek", str(seconds)]

    raise AgentError(f"Unsupported action: {action}")


def action_from_argv(argv: list[str]) -> str:
    return argv[1] if len(argv) > 1 else "unknown"


def positive_int(value: object, default: int | None) -> int:
    if value in (None, ""):
        if default is None:
            raise AgentError("Missing seconds")
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise AgentError(f"Invalid seconds: {value}") from error
    if number < 0:
        raise AgentError(f"Invalid seconds: {value}")
    return number


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise AgentError(f"Missing config file: {path}")

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            continue
        values[key.strip()] = strip_quotes(value.strip())
    return values


def required(config: dict[str, str], key: str) -> str:
    value = config.get(key, "").strip()
    if not value:
        raise AgentError(f"Missing required config: {key}")
    return value


def run_aws_json(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise AgentError(completed.stderr.strip() or f"aws exited {completed.returncode}")
    if not completed.stdout.strip():
        return {}
    return json.loads(completed.stdout)


def strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def shell_word(value: str) -> str:
    return shlex.quote(str(value))


if __name__ == "__main__":
    sys.exit(main())
