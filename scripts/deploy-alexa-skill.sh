#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_FILE="$ROOT_DIR/alexa-skill/skill-package/skill.json"

if ! command -v ask >/dev/null 2>&1; then
  echo "Missing ask CLI. Install it with: npm install -g ask-cli" >&2
  exit 2
fi

if [[ ! -f "$SKILL_FILE" ]]; then
  echo "Missing Alexa skill manifest: $SKILL_FILE" >&2
  exit 2
fi

"$ROOT_DIR/scripts/configure-ask-vendor.sh"

BACKUP_FILE="$(mktemp)"
cp "$SKILL_FILE" "$BACKUP_FILE"
restore_manifest() {
  cp "$BACKUP_FILE" "$SKILL_FILE"
  rm -f "$BACKUP_FILE"
}
trap restore_manifest EXIT

"$ROOT_DIR/scripts/update-alexa-skill-endpoint.sh"

(
  cd "$ROOT_DIR/alexa-skill"
  ask deploy
)

"$ROOT_DIR/scripts/configure-lambda-alexa-trigger.sh"
