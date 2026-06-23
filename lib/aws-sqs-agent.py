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
CODEX_ACTIONS = {"open_codex", "codex_task", "codex_status", "codex_cancel", "codex_quit", "live_codex_prompt"}
BROWSER_ACTIONS = {"browser_open", "browser_search", "browser_command", "browser_seek", "browser_status"}
SURFSHARK_ACTIONS = {"surfshark_disconnect", "surfshark_connect_us"}
MACRO_ACTIONS = {"love_island"}


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
        self.codex_new_chat_on_open = config.get("CODEX_NEW_CHAT_ON_OPEN", "0").strip().lower() not in {"0", "false", "no"}
        self.surfshark_prepare_on_live_prompt = config.get("SURFSHARK_PREPARE_ON_LIVE_PROMPT", "1").strip().lower() not in {"0", "false", "no"}
        self.surfshark_search_point = parse_point(config.get("SURFSHARK_SEARCH_POINT", "325,130"))
        self.surfshark_quick_connect_point = parse_point(config.get("SURFSHARK_QUICK_CONNECT_POINT", "723,501"))
        self.surfshark_quick_connect_relative_point = parse_optional_point(config.get("SURFSHARK_QUICK_CONNECT_RELATIVE_POINT", ""))
        self.surfshark_connect_settle_seconds = float(config.get("SURFSHARK_CONNECT_SETTLE_SECONDS", "12.0"))
        self.click_tool_path = config.get("CLICK_TOOL_PATH") or shutil.which("cliclick") or ""
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
            elif action_name in SURFSHARK_ACTIONS:
                returncode = self.handle_surfshark_action(media_action, message_id)
            elif action_name in MACRO_ACTIONS:
                returncode = self.handle_macro_action(media_action, message_id)
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
        if action == "codex_quit":
            return self.quit_codex(message_id)

        self.log("codex_action_error", message_id=message_id, action=action, error="unsupported_codex_action")
        return 2

    def handle_surfshark_action(self, message: dict[str, object], message_id: str) -> int:
        action = normalized_action(message)
        self.log("surfshark_action_start", message_id=message_id, action=action)
        if not self.click_tool_path:
            self.log("surfshark_action_done", message_id=message_id, action=action, returncode="2", ok="False", stderr="missing_click_tool")
            return 2

        if action in {"surfshark_disconnect", "surfshark_connect_us"}:
            completed = self.quick_connect_surfshark()
        else:
            self.log("surfshark_action_done", message_id=message_id, action=action, returncode="2", ok="False", stderr="unsupported_surfshark_action")
            return 2

        ok = completed.returncode == 0
        self.log(
            "surfshark_action_done",
            message_id=message_id,
            action=action,
            returncode=str(completed.returncode),
            ok=str(ok),
            stderr=completed.stderr.strip(),
        )
        return completed.returncode

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

    def handle_macro_action(self, message: dict[str, object], message_id: str) -> int:
        action = normalized_action(message)
        if action != "love_island":
            self.log("macro_action_error", message_id=message_id, action=action, error="unsupported_macro_action")
            return 2
        return self.run_love_island_macro(message_id)

    def run_love_island_macro(self, message_id: str) -> int:
        self.log("love_island_start", message_id=message_id)

        self.log("love_island_phase", message_id=message_id, phase="vpn_start")
        vpn_ok = False
        if self.click_tool_path:
            vpn_completed = self.quick_connect_surfshark()
            vpn_ok = vpn_completed.returncode == 0
            self.log(
                "love_island_phase",
                message_id=message_id,
                phase="vpn_done",
                returncode=str(vpn_completed.returncode),
                ok=str(vpn_ok),
                stderr=vpn_completed.stderr.strip(),
            )
        else:
            self.log("love_island_phase", message_id=message_id, phase="vpn_done", returncode="2", ok="False", stderr="missing_click_tool")

        if vpn_ok and self.surfshark_connect_settle_seconds > 0:
            time.sleep(self.surfshark_connect_settle_seconds)

        self.log("love_island_phase", message_id=message_id, phase="peacock_open_start")
        peacock_returncode = self.handle_browser_action(
            {"action": "browser_open", "site": "peacock"},
            message_id,
        )
        peacock_ok = peacock_returncode == 0
        self.log(
            "love_island_phase",
            message_id=message_id,
            phase="peacock_opened",
            returncode=str(peacock_returncode),
            ok=str(peacock_ok),
        )

        open_returncode = self.open_codex(message_id)
        if open_returncode != 0:
            self.log("love_island_done", message_id=message_id, returncode=str(open_returncode), ok="False", failed_phase="open_codex")
            return open_returncode

        self.log("love_island_phase", message_id=message_id, phase="fullscreen_check_requested")
        live_prompt = love_island_live_prompt_text(vpn_ok=vpn_ok, peacock_opened=peacock_ok)
        prompt_returncode = self.inject_live_codex_prompt(live_prompt, "love island", message_id)
        prompt_ok = prompt_returncode == 0
        self.log("love_island_phase", message_id=message_id, phase="codex_prompt_sent", returncode=str(prompt_returncode), ok=str(prompt_ok))
        self.log("love_island_done", message_id=message_id, returncode=str(prompt_returncode), ok=str(prompt_ok))
        return prompt_returncode

    def open_codex(self, message_id: str) -> int:
        if not self.codex_workspace.exists():
            self.update_codex_status({"state": "error", "error": "workspace_missing"})
            self.log("codex_open_failed", message_id=message_id, error="workspace_missing")
            return 2

        try:
            subprocess.Popen([self.codex_path, "app", str(self.codex_workspace)], start_new_session=True)
        except OSError as error:
            self.update_codex_status({"state": "error", "error": "codex_open_failed"})
            self.log("codex_open_failed", message_id=message_id, error=str(error))
            return 2

        new_chat_ok = self.open_codex_new_chat() if self.codex_new_chat_on_open else False
        armed_until = int(time.time()) + self.codex_arm_seconds
        self.update_codex_status({
            "state": "armed",
            "armed_until": armed_until,
            "workspace": str(self.codex_workspace),
            "task_pid": None,
            "task_started_at": None,
            "last_prompt": "",
        })
        self.log(
            "codex_opened",
            message_id=message_id,
            armed_until=str(armed_until),
            workspace=str(self.codex_workspace),
            new_chat=str(new_chat_ok),
        )
        return 0

    def open_codex_new_chat(self) -> bool:
        script = [
            'tell application "Codex" to activate',
            "delay 1.0",
            'tell application "System Events"',
            'keystroke "n" using command down',
            "end tell",
        ]
        completed = subprocess.run(
            ["osascript", *sum([["-e", line] for line in script], [])],
            text=True,
            capture_output=True,
            check=False,
        )
        return completed.returncode == 0

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

        surfshark_country = extract_surfshark_country(prompt)
        surfshark_prepared = False
        if self.surfshark_prepare_on_live_prompt and surfshark_country:
            surfshark_prepared = self.prepare_surfshark_country(message_id, surfshark_country)

        live_prompt = live_codex_prompt_text(prompt, surfshark_country=surfshark_country, surfshark_prepared=surfshark_prepared)
        return self.inject_live_codex_prompt(live_prompt, prompt, message_id)

    def inject_live_codex_prompt(self, live_prompt: str, prompt: str, message_id: str) -> int:
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
            ["osascript", *sum([["-e", line] for line in script], []), live_prompt],
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

    def prepare_surfshark_country(self, message_id: str, country: str) -> bool:
        self.log("surfshark_prepare_start", message_id=message_id, country=country)
        if not self.click_tool_path:
            self.log("surfshark_prepare_done", message_id=message_id, country=country, returncode="2", ok="False", stderr="missing_click_tool")
            return False

        if country == "United States":
            completed = self.quick_connect_surfshark()
        else:
            completed = self.search_and_connect_surfshark(country)

        ok = completed.returncode == 0
        self.log(
            "surfshark_prepare_done",
            message_id=message_id,
            country=country,
            returncode=str(completed.returncode),
            ok=str(ok),
            stderr=completed.stderr.strip(),
        )
        return ok

    def quick_connect_surfshark(self) -> subprocess.CompletedProcess[str]:
        completed = self.activate_surfshark()
        if completed.returncode != 0:
            return completed
        completed = self.press_surfshark_quick_connect_button()
        if completed.returncode == 0:
            return completed
        connect_x, connect_y = self.resolve_surfshark_quick_connect_point()
        return subprocess.run(
            [self.click_tool_path, f"c:{connect_x},{connect_y}"],
            text=True,
            capture_output=True,
            check=False,
        )

    def search_and_connect_surfshark(self, country: str) -> subprocess.CompletedProcess[str]:
        search_x, search_y = self.surfshark_search_point
        completed = self.activate_surfshark()
        if completed.returncode != 0:
            return completed
        completed = subprocess.run(
            [self.click_tool_path, f"c:{search_x},{search_y}"],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return completed
        script = [
            "delay 0.3",
            'tell application "System Events"',
            'keystroke "a" using command down',
            "delay 0.1",
            f"keystroke {json.dumps(country)}",
            "delay 0.4",
            "key code 36",
            "delay 1.0",
            "end tell",
        ]
        completed = subprocess.run(
            ["osascript", *sum([["-e", line] for line in script], [])],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return completed
        connect_x, connect_y = self.resolve_surfshark_quick_connect_point()
        return subprocess.run(
            [self.click_tool_path, f"c:{connect_x},{connect_y}"],
            text=True,
            capture_output=True,
            check=False,
        )

    def activate_surfshark(self) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(["open", "-a", "Surfshark"], text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            return completed
        script = [
            'tell application "Surfshark" to activate',
            "delay 0.5",
        ]
        return subprocess.run(
            ["osascript", *sum([["-e", line] for line in script], [])],
            text=True,
            capture_output=True,
            check=False,
        )

    def press_surfshark_quick_connect_button(self) -> subprocess.CompletedProcess[str]:
        script = [
            'tell application "System Events"',
            'if not (exists process "Surfshark") then return "NO_PROCESS"',
            'tell process "Surfshark"',
            'if not (exists window 1) then return "NO_WINDOW"',
            'set targetButtons to buttons of entire contents of window 1 whose name contains "Quick-connect"',
            'if (count of targetButtons) is 0 then set targetButtons to buttons of entire contents of window 1 whose description contains "Quick-connect"',
            'if (count of targetButtons) is 0 then return "NO_BUTTON"',
            'perform action "AXPress" of item 1 of targetButtons',
            'return "PRESSED"',
            'end tell',
            'end tell',
        ]
        completed = subprocess.run(
            ["osascript", *sum([["-e", line] for line in script], [])],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip() == "PRESSED":
            return completed
        return subprocess.CompletedProcess(completed.args, 1, completed.stdout, completed.stderr)

    def resolve_surfshark_quick_connect_point(self) -> tuple[int, int]:
        if self.surfshark_quick_connect_relative_point:
            window_position = self.surfshark_window_position()
            if window_position:
                window_x, window_y = window_position
                relative_x, relative_y = self.surfshark_quick_connect_relative_point
                return window_x + relative_x, window_y + relative_y
        return self.surfshark_quick_connect_point

    def surfshark_window_position(self) -> tuple[int, int] | None:
        script = [
            'tell application "System Events"',
            'if not (exists process "Surfshark") then return "NO_PROCESS"',
            'tell process "Surfshark"',
            'if not (exists window 1) then return "NO_WINDOW"',
            'set p to position of window 1',
            'return ((item 1 of p) as text) & "," & ((item 2 of p) as text)',
            'end tell',
            'end tell',
        ]
        completed = subprocess.run(
            ["osascript", *sum([["-e", line] for line in script], [])],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return None
        try:
            x_text, y_text = completed.stdout.strip().split(",", 1)
            return int(float(x_text)), int(float(y_text))
        except ValueError:
            return None

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

    def quit_codex(self, message_id: str) -> int:
        self.cancel_codex_task(message_id)
        completed = subprocess.run(
            ["osascript", "-e", 'tell application "Codex" to quit'],
            text=True,
            capture_output=True,
            check=False,
        )
        self.update_codex_status({"state": "closed", "task_pid": None})
        self.log(
            "codex_quit",
            message_id=message_id,
            returncode=str(completed.returncode),
            stderr=completed.stderr.strip(),
        )
        return completed.returncode

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


COUNTRY_ALIASES = {
    "usa": "United States",
    "u.s.": "United States",
    "us": "United States",
    "united states": "United States",
    "america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "england": "United Kingdom",
}

COUNTRY_NAMES = [
    "United States",
    "United Kingdom",
    "Canada",
    "Mexico",
    "France",
    "Germany",
    "Italy",
    "Spain",
    "Netherlands",
    "Luxembourg",
    "Australia",
    "Japan",
    "Brazil",
    "Ireland",
    "Switzerland",
    "Sweden",
    "Norway",
    "Denmark",
]


def prompt_requests_surfshark_us(prompt: str) -> bool:
    return extract_surfshark_country(prompt) == "United States"


def extract_surfshark_country(prompt: str) -> str:
    text = prompt.lower()
    wants_vpn = any(term in text for term in ["surfshark", "surf shark", "vpn"])
    if not wants_vpn:
        return ""

    for alias, country in COUNTRY_ALIASES.items():
        if f" {alias} " in f" {text} " or text.endswith(f" {alias}") or text.startswith(f"{alias} "):
            return country

    for country in COUNTRY_NAMES:
        if country.lower() in text:
            return country

    if "peacock" in text:
        return "United States"

    return ""


def live_codex_prompt_text(prompt: str, surfshark_country: str = "", surfshark_prepared: bool = False) -> str:
    surfshark_note = ""
    surfshark_country = surfshark_country or extract_surfshark_country(prompt)
    if surfshark_country:
        if surfshark_prepared:
            surfshark_note = (
                f"\n\nThe Mac helper already opened Surfshark and attempted to connect {surfshark_country} before sending this prompt. "
                "If Surfshark is still asking for login, confirmation, or a manual click, leave Surfshark visible and say what is needed."
            )
        else:
            surfshark_note = (
                f"\n\nThe user requested Surfshark/VPN for {surfshark_country}, but the Mac helper could not confirm it completed. "
                "The known-good manual fallback is: run `osascript -e 'tell application \"Surfshark\" to activate' -e 'delay 0.5'`, "
                "then `/usr/local/bin/cliclick c:723,501` to click Quick-connect in macOS point coordinates. "
                "If Surfshark is visible and needs a manual click/login/confirmation, leave it visible and say what is needed before using Chrome."
            )
    return (
        "User voice prompt: "
        + prompt
        + surfshark_note
        + "\n\nWhen this is a Chrome, streaming, or video playback task, finish by leaving Google Chrome frontmost. "
        "Do not open browser history or other protected local browser data to infer what was recently watched; use the streaming site's visible Continue Watching, search, episode pages, or ask the user if the exact episode cannot be determined without an approval prompt. "
        "If playback has started or a video player is visible, make the player fullscreen before ending. "
        "Before ending, do one final visual/state check that Chrome is frontmost, the intended video page is visible, and the player is actually fullscreen; if the fullscreen click missed, retry once and check again. "
        "If fullscreen is blocked by a login, profile picker, region block, CAPTCHA, or other user-only prompt, leave that page visible in Chrome and say what is needed."
    )


def love_island_live_prompt_text(vpn_ok: bool = False, peacock_opened: bool = False) -> str:
    vpn_note = (
        "Surfshark USA Fastest was attempted."
        if vpn_ok
        else "Surfshark USA Fastest may need checking."
    )
    peacock_note = (
        "Peacock is already open in Chrome."
        if peacock_opened
        else "Open Peacock in Chrome."
    )
    return (
        "Use the resume-love-island-peacock skill now. "
        f"{vpn_note} {peacock_note} "
        "Resume Love Island on Peacock, select Lillia if prompted, play it, and leave Chrome frontmost in fullscreen."
    )


def strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_point(value: str) -> tuple[int, int]:
    x_text, separator, y_text = value.partition(",")
    if not separator:
        raise AgentError(f"Invalid point: {value}")
    return int(x_text.strip()), int(y_text.strip())


def parse_optional_point(value: str) -> tuple[int, int] | None:
    if not value.strip():
        return None
    return parse_point(value)


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
