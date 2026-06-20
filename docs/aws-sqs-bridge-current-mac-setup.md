# AWS SQS Bridge Setup On The TV Mac

Use this path to replace TRIGGERcmd with a free AWS relay:

```text
Alexa custom skill -> Lambda -> SQS -> this Mac LaunchAgent -> safari-remote -> Safari
```

The Mac must be awake and logged in while watching. No browser, open router port,
Cloudflare tunnel, or TRIGGERcmd agent is required after this is working.

## 1. Create The Implementation Goal

When Codex implements or repairs this setup, start with this goal:

```text
Build and verify free AWS SQS Alexa Safari bridge end to end.
```

Loop until the local install, AWS deploy, LaunchAgent, smoke test, docs, commit,
and push are complete.

## 2. Install Local Safari Control

```bash
./install.sh
~/.local/bin/safari-remote selftest
~/.local/bin/safari-remote-prime-permissions
```

Expected:

```text
OK:selftest
Safari automation: OK
Accessibility keystrokes: OK
```

If Accessibility is blocked, allow the runner in:

```text
System Settings > Privacy & Security > Accessibility
```

## 3. Install Required Tools

The deployment script requires:

- AWS CLI v2
- Node.js 18+ and npm
- zip

On a Mac with Homebrew:

```bash
brew install awscli node
```

The Alexa Skills Kit CLI is needed to create/update the custom skill:

```bash
npm install -g ask-cli
```

## 4. Authenticate AWS

Use an AWS account you control. Normal personal use should stay in the Lambda
and SQS free tiers, but create a billing alert before leaving this running.

Authenticate with either:

```bash
aws login
```

or:

```bash
aws configure sso
```

or:

```bash
aws configure
```

Use a setup profile with permission to create SQS queues, Lambda functions, IAM
roles, IAM users, inline policies, and Lambda invoke permissions.

## 5. Deploy The Bridge

```bash
AWS_PROFILE=<your-setup-profile> AWS_REGION=us-east-1 ./scripts/aws-bridge-deploy.sh
```

The script creates or updates:

- SQS queue: `alexa-safari-remote-commands`
- Lambda function: `alexa-safari-remote-skill`
- Lambda role that can only write to the queue plus CloudWatch Logs
- IAM user/profile `alexa-safari-remote-agent` that can only receive/delete from the queue
- Local config: `~/.config/alexa-safari-remote/aws-bridge.env`
- Alexa skill endpoint summary: `alexa-skill/.env.generated`

The script writes agent AWS credentials to the local AWS profile and does not
print access keys.

If an Alexa skill id already exists in `alexa-skill/.ask/ask-states.json`, the
script also keeps the Lambda Alexa trigger scoped to that skill id. On first
deploy, before the skill id exists, the script adds a temporary unscoped Alexa
trigger so the ASK skill import can validate the Lambda endpoint. The skill
deploy script replaces it with the scoped trigger.

## 6. Install The Mac Agent

```bash
./scripts/install-sqs-agent.sh
```

This installs and starts:

```text
~/Library/LaunchAgents/com.alexa-safari-remote.sqs-agent.plist
```

Agent logs:

```text
~/.local/state/alexa-safari-remote/aws-sqs-agent.log
```

Safari command logs:

```text
~/.local/state/alexa-safari-remote/commands.log
```

## 7. Smoke Test

Open a Safari video, then run:

```bash
./scripts/aws-bridge-smoke-test.sh --wait-log
```

Expected:

```text
SMOKE_LAMBDA_OK
SMOKE_AGENT_LOG_UPDATED
```

The final log line in `commands.log` should include:

```text
action=pause args=pause
```

## 8. Alexa Skill Endpoint

Deploying the AWS bridge writes the Lambda endpoint to:

```text
alexa-skill/.env.generated
```

Authenticate the ASK CLI and deploy the skill:

```bash
ask configure
./scripts/deploy-alexa-skill.sh
```

The deploy script:

- fills in the ASK vendor id if `ask configure` authenticated before developer
  enrollment finished
- temporarily writes the real Lambda endpoint into `skill-package/skill.json`
- deploys the ASK package
- restores the placeholder endpoint in the tracked manifest
- scopes the Lambda Alexa trigger to the created skill id

If `ask configure` reports that there is no Vendor ID associated with the
account, open the Alexa Developer Console and finish the one-time developer
account enrollment:

```text
https://developer.amazon.com/alexa/console/ask
```

After the console shows a vendor/developer account, rerun:

```bash
./scripts/configure-ask-vendor.sh
./scripts/deploy-alexa-skill.sh
```

The ASK skill package lives in:

```text
alexa-skill/skill-package/
```

The original interaction model is also kept here for readability:

```text
alexa-skill/interaction-model/en-US.json
```

After the skill is deployed, use the newer Mac handoff guide:

```text
docs/newer-mac-alexa-handoff.md
```

## 9. Alexa-Side Smoke Checks

Useful CLI checks after deploy:

```bash
ask smapi simulate-skill \
  --skill-id "$(node -e 'console.log(require("./alexa-skill/.ask/ask-states.json").profiles.default.skillId)')" \
  --stage development \
  --input-content "open tv remote" \
  --device-locale en-US
```

The launch simulation should return a successful Alexa response. One-shot
commands such as `tell tv remote to pause` can report a generic simulator
failure even when Lambda runs and the Mac command log updates. For this project,
the source of truth is:

```text
~/.local/state/alexa-safari-remote/commands.log
```
