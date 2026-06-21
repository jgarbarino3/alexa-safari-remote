# Alexa To Codex Voice Bridge

This extends the existing Alexa custom skill and SQS Mac agent.

```text
Alexa custom skill -> Lambda -> SQS -> Mac LaunchAgent -> Chrome worker / Codex app / codex exec
```

Safari media commands still use `safari-remote`. Browser and Codex commands use
separate SQS actions:

- `open_codex`
- `codex_task`
- `live_codex_prompt`
- `codex_status`
- `codex_cancel`
- `codex_quit`
- `browser_open`
- `browser_search`
- `browser_command`
- `browser_seek`
- `browser_status`

## Voice Flow

```text
Alexa, open Codex
Alexa, ask Codex to open Peacock
Alexa, ask Codex to search Disney for Andor
Alexa, ask Codex to live Codex use Chrome and find my episode
Alexa, ask Codex for status
Alexa, ask Codex to cancel
Alexa, ask Codex to close Codex
```

The first command opens Codex Desktop and arms prompt intake for 10 minutes. The
browser commands use the local Chrome worker when they match deterministic
open/search/play/seek/fullscreen patterns. Explicit live Codex phrases paste the
prompt into the open Codex app. Other prompts can still use `codex exec`.

After `Alexa, open Codex` or `Alexa, launch Codex`, the skill keeps the Alexa
session open briefly. During that open session, say:

```text
Codex open Chrome and find the episode I was watching
Codex use Chrome and go to Peacock
Codex search Disney for Andor and pick episode 3
Codex open Surfshark USA fastest then open Peacock and play Poker Face
```

Those short in-session phrases are sent through `live_codex_prompt`.
The Mac agent automatically adds a finishing instruction for live Chrome/video
tasks: leave Google Chrome frontmost, and make the player fullscreen when
playback is visible. If a login, profile picker, region block, or CAPTCHA stops
that, Codex should leave the blocker visible in Chrome.

If a live prompt mentions Surfshark/VPN plus USA/United States/Peacock, the Mac
agent first opens Surfshark and makes a best-effort attempt to search/select
United States/Fastest using macOS Accessibility. Surfshark has no confirmed CLI
in this setup, so login prompts, confirmation dialogs, UI changes, or a missing
Accessibility approval may still require the user. The live Codex prompt will
be told whether that prep step was attempted before it continues to Chrome.

## Browser Worker

The Chrome worker is the preferred path for TV/browser actions because it does
not depend on background Codex MCP. It can:

- open common streaming sites or arbitrary URLs in Chrome
- open site search URLs for spoken queries
- send common player keys such as play/pause, fullscreen, escape, and 10-second seek keypresses
- report status in the local agent log

Streaming sites can still block login, CAPTCHA, profile selection, region, or
DRM/player-specific controls. In those cases, the worker logs a clear failure
and the user can handle the visible prompt.

## Mac Agent Behavior

`open_codex` runs:

```bash
codex app "$CODEX_WORKSPACE_PATH"
```

It also arms prompt intake for `CODEX_ARM_SECONDS`, default `600`.
By default it also sends Command-N to Codex after opening, as a best-effort new
chat shortcut. Set `CODEX_NEW_CHAT_ON_OPEN=0` in the local config to disable
that if Codex changes its shortcut behavior.

`codex_task` runs:

```bash
codex exec -C "$CODEX_WORKSPACE_PATH" "$prompt"
```

The task runs in the background so the agent can still receive status and cancel
messages. Only one Codex task runs at a time.

`live_codex_prompt` runs:

```text
focus Codex.app -> paste prompt -> press Return
```

This is the path for more complicated interactive prompts where the live Codex
app can use Chrome tools directly. It requires macOS Accessibility/Automation
approval for the LaunchAgent process and/or terminal wrapper that triggers it.
The injected prompt includes the user's spoken request plus the Chrome
frontmost/fullscreen finishing instruction above.

`codex_status` writes status to the agent log.

`codex_cancel` sends SIGTERM to the running Codex task process group when one is
running.

`codex_quit` cancels any tracked background Codex task and sends Codex.app a
quit Apple Event. Use it when you want the TV Mac to stop showing Codex after a
session:

```text
Alexa, ask Codex to close Codex
```

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
BROWSER_WORKER_PATH=<installed chrome-worker.py path>
LIVE_CODEX_FOCUS_DELAY_SECONDS=0.8
CODEX_NEW_CHAT_ON_OPEN=1
SURFSHARK_PREPARE_ON_LIVE_PROMPT=1
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

The deterministic Chrome worker does not use Codex MCP. It runs local macOS
commands so Alexa browser actions do not stall on interactive MCP recovery.

Live Codex prompt injection is available for complicated browser prompts. That
mode sends the prompt into Codex.app, where a live Codex session can use Chrome
tools normally. It is more powerful, but it depends on UI focus and macOS
Accessibility.

`codex exec` remains useful for repo/local/background prompts, but it is not the
preferred path for complex Chrome interaction because it cannot answer
interactive browser-tool permission or recovery prompts.

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
