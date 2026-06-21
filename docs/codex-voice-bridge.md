# Alexa To Codex Voice Bridge

Use this on the TV Mac after the Safari remote and Alexa relay path are working.

## Voice Flow

```text
Alexa, ask TV remote to open Codex
Alexa, ask TV remote to ask Codex to open Chrome and go to Peacock
Alexa, ask TV remote to Codex status
Alexa, ask TV remote to cancel Codex
```

The first command opens Codex Desktop and arms prompt intake for 10 minutes. The
second command sends the spoken prompt to `codex exec`.

## Local Commands

```bash
codex-voice-bridge open
codex-voice-bridge ask open Chrome and go to example dot com
codex-voice-bridge status
codex-voice-bridge cancel
```

Useful environment variables:

```bash
export ALEXA_CODEX_WORKSPACE="$HOME/Documents/Codex"
export ALEXA_CODEX_ARM_SECONDS=600
export ALEXA_CODEX_TIMEOUT_SECONDS=1800
export ALEXA_CODEX_BIN="$HOME/.local/bin/codex"
```

State and transcripts are written under:

```text
~/.local/state/alexa-safari-remote/codex/
```

The log records event names, prompt length, workspace, result, return code, and
transcript path. It does not record full prompt text beyond a short preview in
state.

## Relay Contract

The Alexa Lambda emits these JSON messages to the configured bridge endpoint:

```json
{ "action": "open_codex" }
{ "action": "codex_task", "prompt": "open Chrome and go to example dot com" }
{ "action": "codex_status" }
{ "action": "codex_cancel" }
```

An SQS polling agent should translate those actions to:

```bash
alexa-bridge-dispatch action.json
```

The agent should delete or acknowledge the queue message after each local
execution attempt, even when the command fails, so a bad command does not loop
forever.

For debugging, inspect the local command without running it:

```bash
alexa-bridge-dispatch --dry-run action.json
```

## Browser Control

The bridge does not automate streaming sites directly. Prompts such as "open
Peacock and search Ted" should be handled by Codex using its Browser Use or
Chrome tooling.

Verify that Codex on the TV Mac can use browser tooling before relying on voice
prompts for streaming-site navigation.

## Surfshark

Browser Use cannot click native macOS app controls. In v1 this repo only exposes
a launch fallback:

```bash
codex-voice-bridge open-surfshark
```

Full Surfshark control requires a scriptable path on the TV Mac, such as a
Surfshark CLI, Shortcuts action, AppleScript support, URL scheme, or a
WireGuard/OpenVPN profile that can be controlled from the shell. If none exists,
VPN connect/disconnect should remain manual or become a separate automation.

## Safety

- Arbitrary prompts require a recent `open_codex` arm command.
- Only one Codex task runs at a time.
- Failed tasks are logged and released; they do not leave the lock file behind.
- `codex exec` keeps Codex's normal sandbox and approval behavior.
- Do not put AWS, GitHub, TRIGGERcmd, or OpenAI tokens in committed files.
