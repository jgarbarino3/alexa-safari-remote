#!/usr/bin/env python3
"""Ensure the ASK CLI profile has a vendor_id without printing it."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=os.environ.get("ASK_DEFAULT_PROFILE", "default"))
    args = parser.parse_args()

    config_path = Path.home() / ".ask" / "cli_config"
    if not config_path.exists():
        raise SystemExit("ASK CLI is not configured yet. Run: ask configure")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    profile = config.setdefault("profiles", {}).setdefault(args.profile, {})
    if profile.get("vendor_id"):
        print("ASK_VENDOR_ID_ALREADY_SET")
        return 0

    explicit_vendor_id = os.environ.get("ALEXA_SAFARI_REMOTE_ASK_VENDOR_ID") or os.environ.get("ASK_VENDOR_ID")
    vendor_id = explicit_vendor_id or get_single_vendor_id(args.profile)
    if not vendor_id:
        raise SystemExit(
            "Could not choose an ASK vendor id automatically. "
            "Set ALEXA_SAFARI_REMOTE_ASK_VENDOR_ID or rerun ask configure."
        )

    profile["vendor_id"] = vendor_id
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print("ASK_VENDOR_ID_SET")
    return 0


def get_single_vendor_id(profile: str) -> str:
    command = ["ask", "smapi", "get-vendor-list", "--profile", profile]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise SystemExit("Could not read ASK vendor list. Run ask configure after Amazon developer enrollment.")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Could not parse ASK vendor list: {exc}") from exc

    vendors = payload.get("vendors") or []
    if len(vendors) != 1:
        return ""

    vendor_id = vendors[0].get("id") or ""
    return vendor_id.strip()


if __name__ == "__main__":
    raise SystemExit(main())
