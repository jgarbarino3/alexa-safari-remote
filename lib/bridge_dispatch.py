#!/usr/bin/env python3
"""Dispatch Alexa bridge JSON actions to local Mac commands."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


class DispatchError(RuntimeError):
    pass


def command_path(env_name: str, default: str) -> str:
    return os.environ.get(env_name, default)


def media_command(action: dict[str, Any]) -> list[str] | None:
    name = action.get("action")
    if name in {"toggle", "play", "pause", "fullscreen", "escape"}:
        return [command_path("SAFARI_REMOTE_BIN", "safari-remote"), name]
    if name in {"back", "forward"}:
        seconds = int(action.get("seconds") or 10)
        return [command_path("SAFARI_REMOTE_BIN", "safari-remote"), name, str(seconds)]
    if name == "seek":
        if "seconds" not in action:
            raise DispatchError("seek action requires seconds")
        return [command_path("SAFARI_REMOTE_BIN", "safari-remote"), "seek", str(int(action["seconds"]))]
    return None


def codex_command(action: dict[str, Any]) -> list[str] | None:
    name = action.get("action")
    bridge = command_path("CODEX_VOICE_BRIDGE_BIN", "codex-voice-bridge")
    if name == "open_codex":
        return [bridge, "open"]
    if name == "codex_task":
        prompt = str(action.get("prompt") or "").strip()
        if not prompt:
            raise DispatchError("codex_task action requires prompt")
        return [bridge, "ask", prompt]
    if name == "codex_status":
        return [bridge, "status"]
    if name == "codex_cancel":
        return [bridge, "cancel"]
    if name == "open_surfshark":
        return [bridge, "open-surfshark"]
    return None


def build_command(action: dict[str, Any]) -> list[str]:
    command = media_command(action) or codex_command(action)
    if command:
        return command
    raise DispatchError(f"Unknown action: {action.get('action')}")


def read_action(path: str | None) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8") if path else sys.stdin.read()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DispatchError(f"Invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise DispatchError("Bridge action must be a JSON object")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dispatch Alexa bridge JSON to local commands.")
    parser.add_argument("path", nargs="?", help="JSON file to dispatch; stdin is used when omitted")
    parser.add_argument("--dry-run", action="store_true", help="Print the local command without running it")
    args = parser.parse_args(argv)

    try:
        action = read_action(args.path)
        command = build_command(action)
        if args.dry_run:
            print(json.dumps(command))
            return 0
        completed = subprocess.run(command, text=True)
        return completed.returncode
    except DispatchError as exc:
        print(f"ERROR:{exc}", file=sys.stderr)
        return 2
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
