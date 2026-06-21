#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${ALEXA_SAFARI_REMOTE_HOME:-$HOME/.local/share/alexa-safari-remote}"
BIN_DIR="${HOME}/.local/bin"

mkdir -p "$INSTALL_DIR/bin" "$INSTALL_DIR/lib" "$BIN_DIR"

cp "$REPO_DIR/bin/safari-remote" "$INSTALL_DIR/bin/safari-remote"
cp "$REPO_DIR/bin/prime-permissions" "$INSTALL_DIR/bin/prime-permissions"
cp "$REPO_DIR/bin/codex-voice-bridge" "$INSTALL_DIR/bin/codex-voice-bridge"
cp "$REPO_DIR/bin/alexa-bridge-dispatch" "$INSTALL_DIR/bin/alexa-bridge-dispatch"
cp "$REPO_DIR/bin/aws-sqs-agent" "$INSTALL_DIR/bin/aws-sqs-agent"
cp "$REPO_DIR/lib/safari-media-control.jxa.js" "$INSTALL_DIR/lib/safari-media-control.jxa.js"
cp "$REPO_DIR/lib/prime-permissions.jxa.js" "$INSTALL_DIR/lib/prime-permissions.jxa.js"
cp "$REPO_DIR/lib/codex_voice_bridge.py" "$INSTALL_DIR/lib/codex_voice_bridge.py"
cp "$REPO_DIR/lib/bridge_dispatch.py" "$INSTALL_DIR/lib/bridge_dispatch.py"
cp "$REPO_DIR/lib/aws_sqs_agent.py" "$INSTALL_DIR/lib/aws_sqs_agent.py"

chmod +x "$INSTALL_DIR/bin/safari-remote" "$INSTALL_DIR/bin/prime-permissions" "$INSTALL_DIR/bin/codex-voice-bridge" "$INSTALL_DIR/bin/alexa-bridge-dispatch" "$INSTALL_DIR/bin/aws-sqs-agent"
chmod +x "$INSTALL_DIR/lib/codex_voice_bridge.py" "$INSTALL_DIR/lib/bridge_dispatch.py" "$INSTALL_DIR/lib/aws_sqs_agent.py"

ln -sf "$INSTALL_DIR/bin/safari-remote" "$BIN_DIR/safari-remote"
ln -sf "$INSTALL_DIR/bin/prime-permissions" "$BIN_DIR/safari-remote-prime-permissions"
ln -sf "$INSTALL_DIR/bin/codex-voice-bridge" "$BIN_DIR/codex-voice-bridge"
ln -sf "$INSTALL_DIR/bin/alexa-bridge-dispatch" "$BIN_DIR/alexa-bridge-dispatch"
ln -sf "$INSTALL_DIR/bin/aws-sqs-agent" "$BIN_DIR/aws-sqs-agent"

cat <<EOF
Installed Alexa Safari Remote.

Commands:
  $BIN_DIR/safari-remote pause
  $BIN_DIR/safari-remote back 10
  $BIN_DIR/safari-remote seek 12:34
  $BIN_DIR/safari-remote-prime-permissions
  $BIN_DIR/codex-voice-bridge open
  $BIN_DIR/codex-voice-bridge ask open example dot com
  $BIN_DIR/alexa-bridge-dispatch --dry-run action.json
  $BIN_DIR/aws-sqs-agent --once

If $BIN_DIR is not on PATH, add this to your shell profile:
  export PATH="\$HOME/.local/bin:\$PATH"
EOF
