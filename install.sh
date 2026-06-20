#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${ALEXA_SAFARI_REMOTE_HOME:-$HOME/.local/share/alexa-safari-remote}"
BIN_DIR="${HOME}/.local/bin"

mkdir -p "$INSTALL_DIR/bin" "$INSTALL_DIR/lib" "$BIN_DIR"

cp "$REPO_DIR/bin/safari-remote" "$INSTALL_DIR/bin/safari-remote"
cp "$REPO_DIR/bin/prime-permissions" "$INSTALL_DIR/bin/prime-permissions"
cp "$REPO_DIR/bin/safari-remote-sqs-agent" "$INSTALL_DIR/bin/safari-remote-sqs-agent"
cp "$REPO_DIR/lib/safari-media-control.jxa.js" "$INSTALL_DIR/lib/safari-media-control.jxa.js"
cp "$REPO_DIR/lib/prime-permissions.jxa.js" "$INSTALL_DIR/lib/prime-permissions.jxa.js"
cp "$REPO_DIR/lib/aws-sqs-agent.py" "$INSTALL_DIR/lib/aws-sqs-agent.py"

chmod +x "$INSTALL_DIR/bin/safari-remote" "$INSTALL_DIR/bin/prime-permissions" "$INSTALL_DIR/bin/safari-remote-sqs-agent"
chmod +x "$INSTALL_DIR/lib/aws-sqs-agent.py"

ln -sf "$INSTALL_DIR/bin/safari-remote" "$BIN_DIR/safari-remote"
ln -sf "$INSTALL_DIR/bin/prime-permissions" "$BIN_DIR/safari-remote-prime-permissions"
ln -sf "$INSTALL_DIR/bin/safari-remote-sqs-agent" "$BIN_DIR/safari-remote-sqs-agent"

cat <<EOF
Installed Alexa Safari Remote.

Commands:
  $BIN_DIR/safari-remote pause
  $BIN_DIR/safari-remote back 10
  $BIN_DIR/safari-remote seek 12:34
  $BIN_DIR/safari-remote-prime-permissions
  $BIN_DIR/safari-remote-sqs-agent --once

If $BIN_DIR is not on PATH, add this to your shell profile:
  export PATH="\$HOME/.local/bin:\$PATH"
EOF
