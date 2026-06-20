#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="${ALEXA_SAFARI_REMOTE_AWS_CONFIG:-$HOME/.config/alexa-safari-remote/aws-bridge.env}"
PLIST="$HOME/Library/LaunchAgents/com.alexa-safari-remote.sqs-agent.plist"
LABEL="com.alexa-safari-remote.sqs-agent"
AGENT_BIN="$HOME/.local/bin/safari-remote-sqs-agent"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing config file: $CONFIG_FILE" >&2
  echo "Run ./scripts/aws-bridge-deploy.sh first." >&2
  exit 2
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "Missing aws CLI. Install AWS CLI v2, then re-run this script." >&2
  exit 2
fi

"$ROOT_DIR/install.sh" >/dev/null

mkdir -p "$HOME/Library/LaunchAgents"

cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$AGENT_BIN</string>
    <string>--config</string>
    <string>$CONFIG_FILE</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$HOME/.local/state/alexa-safari-remote/aws-sqs-agent.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/.local/state/alexa-safari-remote/aws-sqs-agent.stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict>
</plist>
EOF

chmod 600 "$PLIST"
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "Installed and started $LABEL."
echo "Agent log: $HOME/.local/state/alexa-safari-remote/aws-sqs-agent.log"
