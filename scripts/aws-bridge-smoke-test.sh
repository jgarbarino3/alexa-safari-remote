#!/usr/bin/env bash
set -euo pipefail

WAIT_LOG=0
if [[ "${1:-}" == "--wait-log" ]]; then
  WAIT_LOG=1
fi

if [[ -z "${ALEXA_SQS_QUEUE_URL:-}" ]]; then
  echo "ALEXA_SQS_QUEUE_URL is required." >&2
  exit 2
fi

BODY='{"action":"codex_status"}'
aws sqs send-message \
  --queue-url "$ALEXA_SQS_QUEUE_URL" \
  --message-body "$BODY" \
  --output json >/dev/null

echo "Sent smoke message: codex_status"

if [[ "$WAIT_LOG" == "1" ]]; then
  LOG="${ALEXA_SQS_AGENT_LOG:-$HOME/.local/state/alexa-safari-remote/aws-sqs-agent.log}"
  echo "Waiting for log entry in $LOG"
  for _ in {1..30}; do
    if [[ -f "$LOG" ]] && tail -n 20 "$LOG" | grep -q 'action="codex_status"'; then
      tail -n 20 "$LOG"
      exit 0
    fi
    sleep 2
  done
  echo "Timed out waiting for codex_status in $LOG" >&2
  exit 1
fi
