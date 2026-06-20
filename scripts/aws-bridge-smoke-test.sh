#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="${ALEXA_SAFARI_REMOTE_AWS_CONFIG:-$HOME/.config/alexa-safari-remote/aws-bridge.env}"
WAIT_LOG=false

if [[ "${1:-}" == "--wait-log" ]]; then
  WAIT_LOG=true
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing config file: $CONFIG_FILE" >&2
  exit 2
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "Missing aws CLI." >&2
  exit 2
fi

# shellcheck disable=SC1090
source "$CONFIG_FILE"

if [[ -z "${LAMBDA_FUNCTION_NAME:-}" ]]; then
  echo "Missing LAMBDA_FUNCTION_NAME in $CONFIG_FILE" >&2
  exit 2
fi

# The agent config intentionally sets AWS_PROFILE to the receive/delete-only
# polling profile. The smoke test invokes Lambda, so use the deploy/admin
# profile and keep the agent profile out of this process environment.
DEPLOY_PROFILE="${ALEXA_SAFARI_REMOTE_DEPLOY_PROFILE:-${DEPLOY_AWS_PROFILE:-}}"
unset AWS_PROFILE

AWS_ARGS=(--region "${AWS_REGION:-us-east-1}")
if [[ -n "$DEPLOY_PROFILE" ]]; then
  AWS_ARGS+=(--profile "$DEPLOY_PROFILE")
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat >"$TMP_DIR/pause-intent.json" <<'JSON'
{
  "request": {
    "type": "IntentRequest",
    "intent": {
      "name": "PauseIntent",
      "slots": {}
    }
  }
}
JSON

LOG_FILE="$HOME/.local/state/alexa-safari-remote/commands.log"
before=0
if [[ -f "$LOG_FILE" ]]; then
  before="$(wc -l < "$LOG_FILE")"
fi

aws "${AWS_ARGS[@]}" lambda invoke \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --payload "fileb://$TMP_DIR/pause-intent.json" \
  "$TMP_DIR/lambda-response.json" >"$TMP_DIR/lambda-metadata.json"

python3 - <<'PY' "$TMP_DIR/lambda-response.json" "$TMP_DIR/lambda-metadata.json"
import json
import re
import sys


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        raw = handle.read()
    if not raw.strip():
        return {}, raw
    try:
        return json.loads(raw), raw
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid Lambda JSON response: {exc}: {raw[:500]!r}")


def redact(value):
    text = json.dumps(value, sort_keys=True) if not isinstance(value, str) else value
    text = re.sub(r"\b\d{12}\b", "<account-id>", text)
    text = re.sub(
        r"arn:aws:lambda:[a-z0-9-]+:<account-id>:function:[A-Za-z0-9-_]+",
        "arn:aws:lambda:<region>:<account-id>:function:<function>",
        text,
    )
    return text[:1200]


payload, raw_payload = read_json(sys.argv[1])
metadata, _ = read_json(sys.argv[2])
if metadata.get("FunctionError"):
    raise SystemExit(f"Lambda FunctionError: {redact(metadata)} response={redact(raw_payload)}")

text = payload.get("response", {}).get("outputSpeech", {}).get("text", "")
if text != "Paused.":
    raise SystemExit(f"Unexpected Lambda response: {text!r}; payload={redact(payload)}")
print("SMOKE_LAMBDA_OK")
PY

if [[ "$WAIT_LOG" != true ]]; then
  exit 0
fi

for _ in {1..45}; do
  after=0
  if [[ -f "$LOG_FILE" ]]; then
    after="$(wc -l < "$LOG_FILE")"
  fi
  if [[ "$after" -gt "$before" ]]; then
    echo "SMOKE_AGENT_LOG_UPDATED"
    tail -n 3 "$LOG_FILE"
    exit 0
  fi
  sleep 1
done

echo "SMOKE_AGENT_LOG_NOT_UPDATED" >&2
exit 1
