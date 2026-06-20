#!/usr/bin/env python3
"""Copy the deployed Lambda ARN into the local ASK skill manifest."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "alexa-skill" / ".env.generated"
SKILL_FILE = ROOT / "alexa-skill" / "skill-package" / "skill.json"


def main() -> int:
    values = read_env(ENV_FILE) if ENV_FILE.exists() else {}
    lambda_arn = values.get("LAMBDA_ARN", "").strip() or fetch_lambda_arn(values)
    if not lambda_arn:
        raise SystemExit("Missing LAMBDA_ARN. Run aws-bridge-deploy.sh or authenticate AWS first.")

    payload = json.loads(SKILL_FILE.read_text(encoding="utf-8"))
    endpoint = payload["manifest"]["apis"]["custom"]["endpoint"]
    endpoint["uri"] = lambda_arn
    SKILL_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("UPDATED_SKILL_ENDPOINT")
    print(f"Skill manifest: {SKILL_FILE}")
    return 0


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def fetch_lambda_arn(values: dict[str, str]) -> str:
    function_name = os.environ.get("ALEXA_SAFARI_REMOTE_LAMBDA_FUNCTION")
    function_name = function_name or values.get("LAMBDA_FUNCTION_NAME")
    function_name = function_name or "alexa-safari-remote-skill"

    region = os.environ.get("AWS_REGION") or values.get("AWS_REGION") or "us-east-1"
    command = [
        "aws",
        "--region",
        region,
        "lambda",
        "get-function",
        "--function-name",
        function_name,
        "--query",
        "Configuration.FunctionArn",
        "--output",
        "text",
    ]

    profile = os.environ.get("ALEXA_SAFARI_REMOTE_DEPLOY_PROFILE") or values.get("DEPLOY_AWS_PROFILE")
    if profile:
        command[1:1] = ["--profile", profile]

    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
