#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${ALEXA_SQS_QUEUE_URL:-}" ]]; then
  cat >&2 <<'EOF'
ALEXA_SQS_QUEUE_URL is required.

Example:
  export ALEXA_SQS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/123456789012/alexa-safari-remote"
  ./scripts/install-sqs-agent.sh
EOF
  exit 2
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$REPO_DIR/install.sh"

PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST="$PLIST_DIR/local.alexa-safari-remote.aws-sqs-agent.plist"
LOG_DIR="$HOME/.local/state/alexa-safari-remote"
mkdir -p "$PLIST_DIR" "$LOG_DIR"

cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>local.alexa-safari-remote.aws-sqs-agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>$HOME/.local/bin/aws-sqs-agent</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>ALEXA_SQS_QUEUE_URL</key>
    <string>${ALEXA_SQS_QUEUE_URL}</string>
    <key>ALEXA_CODEX_WORKSPACE</key>
    <string>${ALEXA_CODEX_WORKSPACE:-$HOME/Documents/Codex}</string>
    <key>PATH</key>
    <string>$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/aws-sqs-agent.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/aws-sqs-agent.stderr.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"

cat <<EOF
Installed SQS agent LaunchAgent:
  $PLIST

Logs:
  $LOG_DIR/aws-sqs-agent.log
  $LOG_DIR/aws-sqs-agent.stdout.log
  $LOG_DIR/aws-sqs-agent.stderr.log
EOF
