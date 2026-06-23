#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="${ALEXA_SAFARI_REMOTE_AWS_CONFIG:-$HOME/.config/alexa-safari-remote/aws-bridge.env}"
LABEL="com.alexa-safari-remote.sqs-agent"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing config file: $CONFIG_FILE" >&2
  exit 2
fi

if ! command -v cliclick >/dev/null 2>&1; then
  echo "Missing cliclick. Install cliclick, then re-run this script." >&2
  exit 2
fi

set_config_value() {
  local key="$1"
  local value="$2"
  if grep -q "^$key=" "$CONFIG_FILE"; then
    sed -i.bak "s|^$key=.*|$key=$value|" "$CONFIG_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >>"$CONFIG_FILE"
  fi
}

open -a Surfshark
osascript -e 'tell application "Surfshark" to activate' -e 'delay 0.5'

echo "Move the mouse to the center of Surfshark's Quick-connect button, then press Enter here."
read -r _

point="$(cliclick p)"
x="${point%,*}"
y="${point#*,}"
window_position="$(osascript \
  -e 'tell application "System Events"' \
  -e 'tell process "Surfshark"' \
  -e 'set p to position of window 1' \
  -e 'return ((item 1 of p) as text) & "," & ((item 2 of p) as text)' \
  -e 'end tell' \
  -e 'end tell')"
window_x="${window_position%,*}"
window_y="${window_position#*,}"
relative_x=$((x - window_x))
relative_y=$((y - window_y))

set_config_value "SURFSHARK_QUICK_CONNECT_POINT" "$x,$y"
set_config_value "SURFSHARK_QUICK_CONNECT_RELATIVE_POINT" "$relative_x,$relative_y"

launchctl kickstart -k "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true

echo "Updated Surfshark Quick-connect point."
echo "Absolute point: $x,$y"
echo "Window-relative point: $relative_x,$relative_y"
