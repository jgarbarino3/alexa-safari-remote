#!/usr/bin/env python3
"""Local Codex voice bridge used by Alexa relay agents."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ARM_SECONDS = 600
DEFAULT_TIMEOUT_SECONDS = 1800


class BridgeError(RuntimeError):
    """User-facing bridge error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_root() -> Path:
    return Path(os.environ.get("ALEXA_CODEX_STATE_DIR", "~/.local/state/alexa-safari-remote/codex")).expanduser()


def default_workspace() -> Path:
    return Path(os.environ.get("ALEXA_CODEX_WORKSPACE", "~")).expanduser()


def codex_bin() -> str:
    return os.environ.get("ALEXA_CODEX_BIN", "codex")


def arm_seconds() -> int:
    return positive_int(os.environ.get("ALEXA_CODEX_ARM_SECONDS"), DEFAULT_ARM_SECONDS)


def timeout_seconds() -> int:
    return positive_int(os.environ.get("ALEXA_CODEX_TIMEOUT_SECONDS"), DEFAULT_TIMEOUT_SECONDS)


def positive_int(value: str | None, default: int) -> int:
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def read_state(root: Path) -> dict[str, Any]:
    state_file = root / "state.json"
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"corrupt_state": True}


def write_state(root: Path, state: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / "state.json.tmp"
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(root / "state.json")


def append_log(root: Path, event: str, **fields: Any) -> None:
    root.mkdir(parents=True, exist_ok=True)
    safe_fields = " ".join(f"{key}={json.dumps(value, ensure_ascii=True)}" for key, value in fields.items())
    with (root / "codex-bridge.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{utc_now()} event={event}")
        if safe_fields:
            handle.write(f" {safe_fields}")
        handle.write("\n")


class Lock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def __enter__(self) -> "Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise BridgeError("Codex is already running a voice task.") from exc
        os.write(self.fd, str(os.getpid()).encode("ascii"))
        return self

    def __exit__(self, *_: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def is_armed(state: dict[str, Any]) -> bool:
    return float(state.get("armed_until", 0)) > time.time()


def resolve_workspace(value: str | None) -> Path:
    workspace = Path(value).expanduser() if value else default_workspace()
    return workspace.resolve()


def open_codex(args: argparse.Namespace) -> int:
    root = state_root()
    workspace = resolve_workspace(args.workspace)
    duration = args.arm_seconds or arm_seconds()
    command = [codex_bin(), "app", str(workspace)]

    subprocess.run(command, check=True, timeout=args.timeout or 60)

    state = read_state(root)
    state.update(
        {
            "armed_until": time.time() + duration,
            "armed_at": utc_now(),
            "workspace": str(workspace),
            "last_status": "armed",
        }
    )
    write_state(root, state)
    append_log(root, "open_codex", workspace=str(workspace), armed_seconds=duration)
    print(f"OK:open_codex:armed:{duration}")
    return 0


def ask_codex(args: argparse.Namespace) -> int:
    prompt = " ".join(args.prompt).strip()
    if not prompt:
        raise BridgeError("Missing Codex prompt.")

    root = state_root()
    state = read_state(root)
    if not is_armed(state):
        append_log(root, "codex_task_rejected", reason="not_armed")
        raise BridgeError("Codex is not armed. Say open Codex first.")

    workspace = resolve_workspace(args.workspace or state.get("workspace"))
    timeout = args.timeout or timeout_seconds()
    transcript = root / "transcripts" / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
    transcript.parent.mkdir(parents=True, exist_ok=True)

    with Lock(root / "codex-task.lock"):
        state.update(
            {
                "last_status": "running",
                "running_pid": None,
                "running_started_at": utc_now(),
                "last_prompt_preview": prompt[:120],
                "last_transcript": str(transcript),
            }
        )
        write_state(root, state)
        append_log(root, "codex_task_started", workspace=str(workspace), prompt_chars=len(prompt))

        process = subprocess.Popen(
            [codex_bin(), "exec", "-C", str(workspace), prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        state["running_pid"] = process.pid
        write_state(root, state)

        try:
            output, _ = process.communicate(timeout=timeout)
            transcript.write_text(output or "", encoding="utf-8")
            result = "ok" if process.returncode == 0 else "failed"
            state.update(
                {
                    "last_status": result,
                    "last_returncode": process.returncode,
                    "last_finished_at": utc_now(),
                    "running_pid": None,
                }
            )
            write_state(root, state)
            append_log(root, "codex_task_finished", result=result, returncode=process.returncode)
            if process.returncode != 0:
                raise BridgeError(f"Codex task failed with exit code {process.returncode}.")
        except subprocess.TimeoutExpired as exc:
            process.kill()
            output, _ = process.communicate()
            transcript.write_text(output or "", encoding="utf-8")
            state.update(
                {
                    "last_status": "timeout",
                    "last_returncode": None,
                    "last_finished_at": utc_now(),
                    "running_pid": None,
                }
            )
            write_state(root, state)
            append_log(root, "codex_task_timeout", timeout_seconds=timeout)
            raise BridgeError(f"Codex task timed out after {timeout} seconds.") from exc

    print(f"OK:codex_task:{transcript}")
    return 0


def status(_: argparse.Namespace) -> int:
    root = state_root()
    state = read_state(root)
    armed = is_armed(state)
    running_pid = state.get("running_pid")
    status_value = state.get("last_status", "idle")
    if status_value == "armed" and not armed:
        status_value = "expired"
    print(
        json.dumps(
            {
                "status": status_value,
                "armed": armed,
                "running_pid": running_pid,
                "workspace": state.get("workspace"),
                "last_transcript": state.get("last_transcript"),
            },
            sort_keys=True,
        )
    )
    return 0


def cancel(_: argparse.Namespace) -> int:
    root = state_root()
    state = read_state(root)
    pid = state.get("running_pid")
    killed = False
    if isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, signal.SIGTERM)
            killed = True
        except ProcessLookupError:
            killed = False
    state.update({"armed_until": 0, "last_status": "cancelled", "running_pid": None})
    write_state(root, state)
    append_log(root, "cancel_codex", killed=killed)
    print("OK:cancel_codex")
    return 0


def open_surfshark(_: argparse.Namespace) -> int:
    subprocess.run(["open", "-a", "Surfshark"], check=True, timeout=30)
    append_log(state_root(), "open_surfshark")
    print("OK:open_surfshark")
    return 0


def selftest(_: argparse.Namespace) -> int:
    root = state_root()
    root.mkdir(parents=True, exist_ok=True)
    append_log(root, "selftest")
    print("OK:selftest")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge Alexa voice commands to local Codex.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    open_parser = subparsers.add_parser("open", aliases=["arm", "open-codex"])
    open_parser.add_argument("--workspace")
    open_parser.add_argument("--arm-seconds", type=int)
    open_parser.add_argument("--timeout", type=int)
    open_parser.set_defaults(func=open_codex)

    ask_parser = subparsers.add_parser("ask", aliases=["task", "codex-task"])
    ask_parser.add_argument("--workspace")
    ask_parser.add_argument("--timeout", type=int)
    ask_parser.add_argument("prompt", nargs=argparse.REMAINDER)
    ask_parser.set_defaults(func=ask_codex)

    status_parser = subparsers.add_parser("status")
    status_parser.set_defaults(func=status)

    cancel_parser = subparsers.add_parser("cancel")
    cancel_parser.set_defaults(func=cancel)

    surfshark_parser = subparsers.add_parser("open-surfshark")
    surfshark_parser.set_defaults(func=open_surfshark)

    selftest_parser = subparsers.add_parser("selftest")
    selftest_parser.set_defaults(func=selftest)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BridgeError as exc:
        print(f"ERROR:{exc}", file=sys.stderr)
        return 2
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
