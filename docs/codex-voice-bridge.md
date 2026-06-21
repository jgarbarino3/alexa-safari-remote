# Alexa To Codex Voice Bridge

This extends the existing Alexa custom skill and SQS Mac agent.

```text
Alexa custom skill -> Lambda -> SQS -> Mac LaunchAgent -> codex app / codex exec
```

Safari media commands still use `safari-remote`. Codex commands use separate
SQS actions:

- `open_codex`
- `codex_task`
- `codex_status`
- `codex_cancel`

## Voice Flow

The custom skill invocation name remains:

```text
tv remote
```

Direct test phrases:

```text
Alexa, ask tv remote to open codex
Alexa, ask tv remote to ask codex to summarize the repo status
Alexa, ask tv remote to codex status
Alexa, ask tv remote to cancel codex
```

For natural phrases such as `Alexa, open Codex`, create Alexa routines that map
the short phrase to the custom skill phrase. Alexa custom skills do not receive
arbitrary global speech unless Alexa routes the speech to the skill.

## Mac Agent Behavior

`open_codex` runs:

```bash
codex app "$CODEX_WORKSPACE_PATH"
```

It also arms prompt intake for `CODEX_ARM_SECONDS`, default `600`.

`codex_task` runs:

```bash
codex exec -C "$CODEX_WORKSPACE_PATH" "$prompt"
```

The task runs in the background so the agent can still receive status and cancel
messages. Only one Codex task runs at a time.

`codex_status` writes status to the agent log.

`codex_cancel` sends SIGTERM to the running Codex task process group when one is
running.

## Config

The installer appends these non-secret keys to:

```text
~/.config/alexa-safari-remote/aws-bridge.env
```

Only missing keys are added; AWS credentials and queue settings are not
rewritten.

```text
CODEX_WORKSPACE_PATH=<repo path>
CODEX_CLI_PATH=<codex binary path>
CODEX_ARM_SECONDS=600
CODEX_TASK_TIMEOUT_SECONDS=600
```

## Logs

Agent log:

```text
~/.local/state/alexa-safari-remote/aws-sqs-agent.log
```

Codex state:

```text
~/.local/state/alexa-safari-remote/codex/status.json
```

Codex transcript index:

```text
~/.local/state/alexa-safari-remote/codex/transcripts.log
```

Per-task transcript files:

```text
~/.local/state/alexa-safari-remote/codex/task-*.log
```

## Browser And Chrome Use

Browser/Chrome Use belongs inside the Codex prompt execution, not inside this
bridge. The bridge only hands the spoken prompt to `codex exec`. If the local
Codex installation has Browser or Chrome plugins configured, Codex can use them
according to its normal tool and approval behavior.

## Surfshark

This Mac has `/Applications/Surfshark.app` and URL schemes including
`surfshark` and `com.surfshark.vpnclient.macos.direct`. No Surfshark CLI binary
was found in `PATH`, no matching Shortcut was found, and AppleScript dictionary
inspection could not confirm native script commands with the current command
line tools setup.

V1 does not implement native Surfshark VPN control. A safe fallback is opening
the Surfshark app or URL scheme for manual GUI control.

## Safety Notes

The SQS agent deletes every received message after attempting it, even when the
local command fails. This prevents poison-message loops from blocking later
commands.

`codex exec` runs with normal local Codex configuration, sandbox, and approval
behavior. Non-interactive `codex exec` cannot answer prompts in this chat; if a
task requires approval, the task may pause/fail according to Codex CLI behavior.
