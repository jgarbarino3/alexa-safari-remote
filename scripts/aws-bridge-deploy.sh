#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESOURCE_PREFIX="${ALEXA_SAFARI_REMOTE_PREFIX:-alexa-safari-remote}"
AWS_REGION="${AWS_REGION:-us-east-1}"

QUEUE_NAME="${RESOURCE_PREFIX}-commands"
FUNCTION_NAME="${RESOURCE_PREFIX}-skill"
LAMBDA_ROLE_NAME="${RESOURCE_PREFIX}-lambda-role"
AGENT_USER_NAME="${RESOURCE_PREFIX}-agent"
AGENT_PROFILE_NAME="${ALEXA_SAFARI_REMOTE_AGENT_PROFILE:-alexa-safari-remote-agent}"
LAMBDA_TIMEOUT_SECONDS="${ALEXA_SAFARI_REMOTE_LAMBDA_TIMEOUT_SECONDS:-10}"
CONFIG_DIR="$HOME/.config/alexa-safari-remote"
CONFIG_FILE="$CONFIG_DIR/aws-bridge.env"
BUILD_DIR="$ROOT_DIR/.aws-bridge-build"
PACKAGE_DIR="$BUILD_DIR/lambda-package"
ZIP_FILE="$BUILD_DIR/lambda.zip"
ASK_STATE_FILE="$ROOT_DIR/alexa-skill/.ask/ask-states.json"

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 2
  fi
}

aws_cmd() {
  if [[ -n "${AWS_PROFILE:-}" ]]; then
    aws --profile "$AWS_PROFILE" --region "$AWS_REGION" "$@"
  else
    aws --region "$AWS_REGION" "$@"
  fi
}

aws_iam() {
  if [[ -n "${AWS_PROFILE:-}" ]]; then
    aws --profile "$AWS_PROFILE" iam "$@"
  else
    aws iam "$@"
  fi
}

need aws
need node
need npm
need python3
need zip

set +e
aws_cmd sts get-caller-identity >/dev/null 2>&1
AUTH_STATUS=$?
set -e
if [[ "$AUTH_STATUS" -ne 0 ]]; then
  cat >&2 <<EOF
AWS credentials are not configured for this shell.

Run one of these, then retry:
  aws login
  aws configure sso
  aws configure

If you use a named setup profile:
  AWS_PROFILE=<your-setup-profile> AWS_REGION=$AWS_REGION ./scripts/aws-bridge-deploy.sh
EOF
  exit 3
fi

echo "Deploying AWS bridge in region $AWS_REGION."

QUEUE_URL="$(aws_cmd sqs create-queue \
  --queue-name "$QUEUE_NAME" \
  --attributes VisibilityTimeout=45,ReceiveMessageWaitTimeSeconds=20 \
  --query QueueUrl \
  --output text)"

QUEUE_ARN="$(aws_cmd sqs get-queue-attributes \
  --queue-url "$QUEUE_URL" \
  --attribute-names QueueArn \
  --query 'Attributes.QueueArn' \
  --output text)"

mkdir -p "$BUILD_DIR"

cat >"$BUILD_DIR/lambda-trust-policy.json" <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON

if ! aws_iam get-role --role-name "$LAMBDA_ROLE_NAME" >/dev/null 2>&1; then
  aws_iam create-role \
    --role-name "$LAMBDA_ROLE_NAME" \
    --assume-role-policy-document "file://$BUILD_DIR/lambda-trust-policy.json" >/dev/null
  sleep 10
fi

LAMBDA_ROLE_ARN="$(aws_iam get-role \
  --role-name "$LAMBDA_ROLE_NAME" \
  --query 'Role.Arn' \
  --output text)"

cat >"$BUILD_DIR/lambda-policy.json" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "sqs:SendMessage",
      "Resource": "$QUEUE_ARN"
    }
  ]
}
JSON

aws_iam put-role-policy \
  --role-name "$LAMBDA_ROLE_NAME" \
  --policy-name "${RESOURCE_PREFIX}-lambda-policy" \
  --policy-document "file://$BUILD_DIR/lambda-policy.json"

rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"
cp "$ROOT_DIR/alexa-skill/lambda/index.js" \
  "$ROOT_DIR/alexa-skill/lambda/package.json" \
  "$ROOT_DIR/alexa-skill/lambda/package-lock.json" \
  "$PACKAGE_DIR/"
(cd "$PACKAGE_DIR" && npm install --omit=dev >/dev/null)
(cd "$PACKAGE_DIR" && zip -qr "$ZIP_FILE" .)

if aws_cmd lambda get-function --function-name "$FUNCTION_NAME" >/dev/null 2>&1; then
  aws_cmd lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file "fileb://$ZIP_FILE" >/dev/null
  aws_cmd lambda wait function-updated --function-name "$FUNCTION_NAME"
  aws_cmd lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --runtime nodejs20.x \
    --handler index.handler \
    --role "$LAMBDA_ROLE_ARN" \
    --timeout "$LAMBDA_TIMEOUT_SECONDS" \
    --environment "Variables={ALEXA_SAFARI_REMOTE_QUEUE_URL=$QUEUE_URL}" >/dev/null
  aws_cmd lambda wait function-updated --function-name "$FUNCTION_NAME"
else
  aws_cmd lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime nodejs20.x \
    --handler index.handler \
    --role "$LAMBDA_ROLE_ARN" \
    --timeout "$LAMBDA_TIMEOUT_SECONDS" \
    --zip-file "fileb://$ZIP_FILE" \
    --environment "Variables={ALEXA_SAFARI_REMOTE_QUEUE_URL=$QUEUE_URL}" >/dev/null
  aws_cmd lambda wait function-active --function-name "$FUNCTION_NAME"
fi

LAMBDA_ARN="$(aws_cmd lambda get-function \
  --function-name "$FUNCTION_NAME" \
  --query 'Configuration.FunctionArn' \
  --output text)"

SKILL_ID=""
if [[ -f "$ASK_STATE_FILE" ]]; then
  SKILL_ID="$(node - <<'NODE' "$ASK_STATE_FILE"
const fs = require("fs");
try {
  const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  process.stdout.write(payload.profiles?.default?.skillId || "");
} catch {
  process.stdout.write("");
}
NODE
)"
fi

if [[ -n "$SKILL_ID" ]]; then
  aws_cmd lambda remove-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id AlexaSkillKitInvokeScoped >/dev/null 2>&1 || true
  aws_cmd lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id AlexaSkillKitInvokeScoped \
    --action lambda:InvokeFunction \
    --principal alexa-appkit.amazon.com \
    --event-source-token "$SKILL_ID" >/dev/null
  aws_cmd lambda remove-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id AlexaSkillKitInvoke >/dev/null 2>&1 || true
else
  aws_cmd lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id AlexaSkillKitInvoke \
    --action lambda:InvokeFunction \
    --principal alexa-appkit.amazon.com >/dev/null 2>&1 || true
fi

if ! aws_iam get-user --user-name "$AGENT_USER_NAME" >/dev/null 2>&1; then
  aws_iam create-user --user-name "$AGENT_USER_NAME" >/dev/null
fi

cat >"$BUILD_DIR/agent-policy.json" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "$QUEUE_ARN"
    }
  ]
}
JSON

aws_iam put-user-policy \
  --user-name "$AGENT_USER_NAME" \
  --policy-name "${RESOURCE_PREFIX}-agent-policy" \
  --policy-document "file://$BUILD_DIR/agent-policy.json"

mkdir -p "$HOME/.aws" "$CONFIG_DIR"
chmod 700 "$HOME/.aws" "$CONFIG_DIR"

if ! aws configure get aws_access_key_id --profile "$AGENT_PROFILE_NAME" >/dev/null 2>&1; then
  ACCESS_KEY_JSON="$(aws_iam create-access-key --user-name "$AGENT_USER_NAME" --output json)"
  ACCESS_KEY_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["AccessKey"]["AccessKeyId"])' <<<"$ACCESS_KEY_JSON")"
  SECRET_ACCESS_KEY="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["AccessKey"]["SecretAccessKey"])' <<<"$ACCESS_KEY_JSON")"

  aws configure set aws_access_key_id "$ACCESS_KEY_ID" --profile "$AGENT_PROFILE_NAME"
  aws configure set aws_secret_access_key "$SECRET_ACCESS_KEY" --profile "$AGENT_PROFILE_NAME"
  aws configure set region "$AWS_REGION" --profile "$AGENT_PROFILE_NAME"
  chmod 600 "$HOME/.aws/credentials" "$HOME/.aws/config" 2>/dev/null || true
fi

cat >"$CONFIG_FILE" <<EOF
AWS_REGION=$AWS_REGION
DEPLOY_AWS_PROFILE=${AWS_PROFILE:-}
AWS_PROFILE=$AGENT_PROFILE_NAME
QUEUE_URL=$QUEUE_URL
LAMBDA_FUNCTION_NAME=$FUNCTION_NAME
WAIT_TIME_SECONDS=20
VISIBILITY_TIMEOUT_SECONDS=45
SAFARI_REMOTE_PATH=$HOME/.local/bin/safari-remote
EOF
chmod 600 "$CONFIG_FILE"

cat >"$ROOT_DIR/alexa-skill/.env.generated" <<EOF
AWS_REGION=$AWS_REGION
QUEUE_URL=$QUEUE_URL
LAMBDA_FUNCTION_NAME=$FUNCTION_NAME
LAMBDA_ARN=$LAMBDA_ARN
EOF
chmod 600 "$ROOT_DIR/alexa-skill/.env.generated"

cat <<EOF
AWS bridge deployed.

Lambda ARN for the Alexa skill endpoint:
  $LAMBDA_ARN

Local agent config:
  $CONFIG_FILE

Next:
  ./scripts/install-sqs-agent.sh
  ./scripts/aws-bridge-smoke-test.sh --wait-log
EOF
