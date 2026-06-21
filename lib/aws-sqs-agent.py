#!/usr/bin/env python3
"""Long-poll an SQS queue and run safari-remote commands."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_CONFIG = Path.home() / ".config" / "alexa-safari-remote" / "aws-bridge.env"
DEFAULT_LOG = Path.home() / ".local" / "state" / "alexa-safari-remote" / "aws-sqs-agent.log"
DEFAULT_SAFARI_REMOTE = Path.home() / ".local" / "bin" / "safari-remote"
DEFAULT_CODEX_STATE_DIR = Path.home() / ".local" / "state" / "alexa-safari-remote" / "codex"
DEFAULT_BROWSER_WORKER = Path.home() / ".local" / "share" / "alexa-safari-remote" / "lib" / "chrome-worker.py"
CODEX_ACTIONS = {"open_codex", "codex_task", "codex_status", "codex_cancel", "live_codex_prompt"}
BROWSER_ACTIONS = {"browser_open", "browser_search", "browser_command", "browser_seek", "browser_status"}


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
        self.codex_workspace = Path(config.get("CODEX_WORKSPACE_PATH", str(Path.home()))).expanduser()
        self.codex_path = config.get("CODEX_CLI_PATH") or shutil.which("codex") or "/Applications/Codex.app/Contents/Resources/codex"
        self.codex_arm_seconds = int(config.get("CODEX_ARM_SECONDS", "600"))
        self.codex_task_timeout = int(config.get("CODEX_TASK_TIMEOUT_SECONDS", "600"))
        self.codex_state_dir = Path(config.get("CODEX_STATE_DIR", str(DEFAULT_CODEX_STATE_DIR))).expanduser()
        self.browser_worker = Path(config.get("BROWSER_WORKER_PATH", str(DEFAULT_BROWSER_WORKER))).expanduser()
        self.live_codex_delay = float(config.get("LIVE_CODEX_FOCUS_DELAY_SECONDS", "0.8"))
        self.codex_status_file = self.codex_state_dir / "status.json"
        self.codex_lock_file = self.codex_state_dir / "task.lock"
        self.codex_transcript_log = self.codex_state_dir / "transcripts.log"

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
            action_name = normalized_action(media_action)
        except Exception as error:
            self.log("invalid_message", message_id=message_id, error=str(error))
            if receipt_handle:
                self.delete_message(str(receipt_handle))
            return 2

        try:
            if action_name in CODEX_ACTIONS:
                returncode = self.handle_codex_action(media_action, message_id)
            elif action_name in BROWSER_ACTIONS:
                returncode = self.handle_browser_action(media_action, message_id)
            else:
                argv = command_for_message(media_action, self.safari_remote)
                returncode = self.run_safari_command(argv, message_id)
        except Exception as error:
            self.log("command_error", message_id=message_id, action=action_name, error=str(error))
            returncode = 1

        if receipt_handle:
            self.delete_message(str(receipt_handle))
            self.log("message_deleted", message_id=message_id, action=action_name)

        return returncode

    def run_safari_command(self, argv: list[str], message_id: str) -> int:
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
        return completed.returncode

    def handle_codex_action(self, message: dict[str, object], message_id: str) -> int:
        self.codex_state_dir.mkdir(parents=True, exist_ok=True)
        self.reap_codex_task()

        action = normalized_action(message)
        self.log("codex_action_start", message_id=message_id, action=action)

        if action == "open_codex":
            return self.open_codex(message_id)
        if action == "codex_task":
            return self.start_codex_task(str(message.get("prompt", "")).strip(), message_id)
        if action == "live_codex_prompt":
            return self.send_live_codex_prompt(str(message.get("prompt", "")).strip(), message_id)
        if action == "codex_status":
            return self.write_codex_status_event("status_requested", message_id)
        if action == "codex_cancel":
            return self.cancel_codex_task(message_id)

        self.log("codex_action_error", message_id=message_id, action=action, error="unsupported_codex_action")
        return 2

    def handle_browser_action(self, message: dict[str, object], message_id: str) -> int:
        self.log("browser_action_start", message_id=message_id, action=normalized_action(message))
        completed = subprocess.run(
            [sys.executable, str(self.browser_worker), "--message", json.dumps(message)],
            text=True,
            capture_output=True,
            check=False,
        )
        summary = parse_worker_summary(completed.stdout)
        fields = {
            "message_id": message_id,
            "action": normalized_action(message),
            "returncode": str(completed.returncode),
            "worker_event": str(summary.get("event", "")),
            "worker_ok": str(summary.get("ok", "")),
            "stderr": completed.stderr.strip(),
        }
        if summary.get("error"):
            fields["error"] = str(summary["error"])
        if summary.get("site"):
            fields["site"] = str(summary["site"])
        if summary.get("command"):
            fields["command"] = str(summary["command"])
        self.log("browser_action_done", **fields)
        return completed.returncode

    def open_codex(self, message_id: str) -> int:
        if not self.codex_workspace.exists():
            self.update_codex_status({"state": "error", "error": "workspace_missing"})
            self.log("codex_open_failed", message_id=message_id, error="workspace_missing")
            return 2

        subprocess.Popen([self.codex_path, "app", str(self.codex_workspace)], start_new_session=True)
        armed_until = int(time.time()) + self.codex_arm_seconds
        self.update_codex_status({
            "state": "armed",
            "armed_until": armed_until,
            "workspace": str(self.codex_workspace),
            "task_pid": None,
            "task_started_at": None,
            "last_prompt": "",
        })
        self.log("codex_opened", message_id=message_id, armed_until=str(armed_until), workspace=str(self.codex_workspace))
        return 0

    def start_codex_task(self, prompt: str, message_id: str) -> int:
        if not prompt:
            self.log("codex_task_rejected", message_id=message_id, reason="missing_prompt")
            self.write_codex_status_event("task_rejected_missing_prompt", message_id)
            return 2
        if not self.codex_is_armed():
            self.log("codex_task_rejected", message_id=message_id, reason="not_armed")
            self.write_codex_status_event("task_rejected_not_armed", message_id)
            return 3
        if self.codex_lock_file.exists():
            self.log("codex_task_rejected", message_id=message_id, reason="task_running")
            self.write_codex_status_event("task_rejected_task_running", message_id)
            return 4

        transcript_path = self.codex_state_dir / f"task-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
        transcript_handle = transcript_path.open("a", encoding="utf-8")
        transcript_handle.write(f"{utc_now()} event=task_start prompt={shell_word(prompt)}\n")
        transcript_handle.flush()

        process = subprocess.Popen(
            [self.codex_path, "exec", "-C", str(self.codex_workspace), prompt],
            stdout=transcript_handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        transcript_handle.close()

        self.codex_lock_file.write_text(str(process.pid), encoding="utf-8")
        self.update_codex_status({
            "state": "running",
            "armed_until": self.read_codex_status().get("armed_until"),
            "workspace": str(self.codex_workspace),
            "task_pid": process.pid,
            "task_started_at": int(time.time()),
            "task_timeout_seconds": self.codex_task_timeout,
            "transcript": str(transcript_path),
            "last_prompt": prompt,
        })
        with self.codex_transcript_log.open("a", encoding="utf-8") as handle:
            handle.write(f"{utc_now()} event=task_queued pid={process.pid} transcript={shell_word(str(transcript_path))}\n")
        self.log("codex_task_started", message_id=message_id, pid=str(process.pid), transcript=str(transcript_path))
        return 0

    def send_live_codex_prompt(self, prompt: str, message_id: str) -> int:
        if not prompt:
            self.log("live_codex_rejected", message_id=message_id, reason="missing_prompt")
            self.write_codex_status_event("live_prompt_rejected_missing_prompt", message_id)
            return 2
        if not self.codex_is_armed():
            self.log("live_codex_rejected", message_id=message_id, reason="not_armed")
            self.write_codex_status_event("live_prompt_rejected_not_armed", message_id)
            return 3

        script = [
            'on run argv',
            'set promptText to item 1 of argv',
            'tell application "Codex" to activate',
            f"delay {self.live_codex_delay}",
            "set the clipboard to promptText",
            'tell application "System Events"',
            'keystroke "v" using command down',
            "delay 0.1",
            "key code 36",
            "end tell",
            "end run",
        ]
        completed = subprocess.run(
            ["osascript", *sum([["-e", line] for line in script], []), prompt],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0:
            self.update_codex_status({"state": "live_prompt_sent", "last_prompt": prompt})
            self.log("live_codex_prompt_sent", message_id=message_id, prompt_chars=str(len(prompt)))
        else:
            self.update_codex_status({"state": "live_prompt_error", "last_prompt": prompt})
            self.log(
                "live_codex_prompt_failed",
                message_id=message_id,
                returncode=str(completed.returncode),
                stderr=completed.stderr.strip(),
            )
        return completed.returncode

    def cancel_codex_task(self, message_id: str) -> int:
        status = self.read_codex_status()
        pid = int(status.get("task_pid") or 0)
        if pid and process_is_running(pid):
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            self.update_codex_status({"state": "cancelled", "task_pid": None})
            self.clear_codex_lock()
            self.log("codex_task_cancelled", message_id=message_id, pid=str(pid))
            return 0

        self.update_codex_status({"state": "idle", "task_pid": None})
        self.clear_codex_lock()
        self.log("codex_cancel_no_task", message_id=message_id)
        return 0

    def reap_codex_task(self) -> None:
        status = self.read_codex_status()
        pid = int(status.get("task_pid") or 0)
        started_at = int(status.get("task_started_at") or 0)
        if pid <= 0:
            self.clear_codex_lock_if_stale(pid)
            return

        if not process_is_running(pid):
            self.update_codex_status({"state": "finished", "task_pid": None})
            self.clear_codex_lock()
            return

        if started_at and time.time() - started_at > self.codex_task_timeout:
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            self.update_codex_status({"state": "timeout", "task_pid": None})
            self.clear_codex_lock()
            self.log("codex_task_timeout", pid=str(pid))

    def codex_is_armed(self) -> bool:
        status = self.read_codex_status()
        return int(status.get("armed_until") or 0) >= int(time.time())

    def write_codex_status_event(self, event: str, message_id: str) -> int:
        status = self.read_codex_status()
        self.log("codex_status", message_id=message_id, state=str(status.get("state", "unknown")), status_event=event)
        return 0

    def read_codex_status(self) -> dict[str, object]:
        if not self.codex_status_file.exists():
            return {}
        try:
            return json.loads(self.codex_status_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"state": "error", "error": "invalid_status_json"}

    def update_codex_status(self, updates: dict[str, object]) -> None:
        self.codex_state_dir.mkdir(parents=True, exist_ok=True)
        status = self.read_codex_status()
        status.update(updates)
        status["updated_at"] = utc_now()
        self.codex_status_file.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def clear_codex_lock_if_stale(self, pid: int) -> None:
        if self.codex_lock_file.exists() and (pid <= 0 or not process_is_running(pid)):
            self.clear_codex_lock()

    def clear_codex_lock(self) -> None:
        try:
            self.codex_lock_file.unlink()
        except FileNotFoundError:
            pass

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
    action = normalized_action(message)
    if action in {"play", "pause", "toggle", "fullscreen", "escape"}:
        return [str(safari_remote), action]

    if action in {"back", "forward"}:
        seconds = positive_int(message.get("seconds"), default=10)
        return [str(safari_remote), action, str(seconds)]

    if action == "seek":
        seconds = positive_int(message.get("seconds"), default=None)
        return [str(safari_remote), "seek", str(seconds)]

    raise AgentError(f"Unsupported action: {action}")


def normalized_action(message: dict[str, object]) -> str:
    return str(message.get("action", "")).strip().lower()


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


def parse_worker_summary(stdout: str) -> dict[str, object]:
    for line in reversed(stdout.splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def shell_word(value: str) -> str:
    return shlex.quote(str(value))


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def process_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


if __name__ == "__main__":
    sys.exit(main())
