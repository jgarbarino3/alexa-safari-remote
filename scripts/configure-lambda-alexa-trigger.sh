#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="${ALEXA_SAFARI_REMOTE_AWS_CONFIG:-$HOME/.config/alexa-safari-remote/aws-bridge.env}"
STATE_FILE="$ROOT_DIR/alexa-skill/.ask/ask-states.json"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing AWS bridge config: $CONFIG_FILE" >&2
  exit 2
fi

if [[ ! -f "$STATE_FILE" ]]; then
  echo "Missing ASK state file: $STATE_FILE" >&2
  exit 2
fi

# shellcheck disable=SC1090
source "$CONFIG_FILE"

if [[ -z "${LAMBDA_FUNCTION_NAME:-}" ]]; then
  echo "Missing LAMBDA_FUNCTION_NAME in $CONFIG_FILE" >&2
  exit 2
fi

SKILL_ID="$(node - <<'NODE' "$STATE_FILE"
const fs = require("fs");
const path = process.argv[2];
const payload = JSON.parse(fs.readFileSync(path, "utf8"));
process.stdout.write(payload.profiles?.default?.skillId || "");
NODE
)"

if [[ -z "$SKILL_ID" ]]; then
  echo "Missing Alexa skill id in $STATE_FILE" >&2
  exit 2
fi

DEPLOY_PROFILE="${ALEXA_SAFARI_REMOTE_DEPLOY_PROFILE:-${DEPLOY_AWS_PROFILE:-}}"
unset AWS_PROFILE

AWS_ARGS=(--region "${AWS_REGION:-us-east-1}")
if [[ -n "$DEPLOY_PROFILE" ]]; then
  AWS_ARGS+=(--profile "$DEPLOY_PROFILE")
fi

aws "${AWS_ARGS[@]}" lambda remove-permission \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --statement-id AlexaSkillKitInvokeScoped >/dev/null 2>&1 || true

aws "${AWS_ARGS[@]}" lambda add-permission \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --statement-id AlexaSkillKitInvokeScoped \
  --action lambda:InvokeFunction \
  --principal alexa-appkit.amazon.com \
  --event-source-token "$SKILL_ID" >/dev/null

aws "${AWS_ARGS[@]}" lambda remove-permission \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --statement-id AlexaSkillKitInvoke >/dev/null 2>&1 || true

echo "LAMBDA_ALEXA_TRIGGER_SCOPED"
