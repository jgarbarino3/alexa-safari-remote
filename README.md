# Alexa Safari Remote

Voice-control Safari playback on a Mac while the Mac is HDMI-connected to a TV.

The first working path is:

```text
Alexa -> TRIGGERcmd -> safari-remote -> Safari video
```

The preferred no-rate-limit path is:

```text
Alexa custom skill -> AWS Lambda -> SQS -> Mac agent -> safari-remote -> Safari video
```

## What It Controls

The local command supports:

- `play`
- `pause`
- `toggle`
- `back 10`
- `forward 10`
- `seek 12:34`
- `fullscreen`
- `escape`
- `selftest`

It first tries to control the active HTML5 `<video>` element in Safari. That is the reliable path for streaming sites with different button layouts, because it changes the actual video state instead of clicking on Peacock, Disney, Netflix, or YouTube controls by coordinate.

If page-level video control is blocked, it falls back to Safari keyboard controls:

- space for play/pause
- left/right arrows for rewind/forward
- `f` for fullscreen
- escape to leave fullscreen

Exact seek needs the HTML5 video path. Keyboard fallback cannot reliably jump to an arbitrary timestamp across all streaming sites.

## Install On A Mac

This is Intel and Apple Silicon compatible. It uses built-in macOS tools: Bash, Safari, `osascript`, and JavaScript for Automation.

```bash
git clone https://github.com/jgarbarino3/alexa-safari-remote.git
cd alexa-safari-remote
./install.sh
```

The installer creates:

```text
~/.local/bin/safari-remote
~/.local/bin/safari-remote-prime-permissions
~/.local/share/alexa-safari-remote/
```

If `~/.local/bin` is not on your `PATH`, add this to your shell profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Approve Mac Permissions

Safari control needs two macOS approvals.

### 1. Safari JavaScript From Apple Events

In Safari:

1. Safari > Settings > Advanced
2. Enable "Show features for web developers"
3. Develop menu > Allow JavaScript from Apple Events

This is required for exact video control and timestamp seeks.

### 2. Accessibility For The Runner

Run:

```bash
safari-remote-prime-permissions
```

macOS should ask for Automation and/or Accessibility approval. If it does not, open:

```text
System Settings > Privacy & Security > Accessibility
```

Approve the app that will run the command:

- Terminal, while testing manually
- TRIGGERcmd, when Alexa triggers it
- any future local bridge app

The primer sends a harmless Escape keystroke to trigger the Accessibility path.

## Test Locally

Open Safari, start a video, then run:

```bash
safari-remote pause
safari-remote play
safari-remote back 10
safari-remote forward 10
safari-remote seek 12:34
safari-remote fullscreen
safari-remote escape
safari-remote selftest
```

Successful HTML5 control returns values like:

```text
OK:pause:123
OK:back:113
OK:seek:754
```

Fallback keyboard control returns values like:

```text
FALLBACK_KEYS:back:1:NO_VIDEO
```

Every `safari-remote` invocation appends a local audit line here:

```text
~/.local/state/alexa-safari-remote/commands.log
```

That log is intentionally minimal: timestamp, action, and command arguments only.
It is useful for confirming whether Alexa/TRIGGERcmd reached the Mac.

## TRIGGERcmd Setup

TRIGGERcmd remains a useful fallback because it is quick to set up and uses the
Alexa Smart Home skill. Its free plan can be rate-limited for rapid TV controls,
so the AWS SQS bridge is the preferred path once local Safari control is proven.

Install the TRIGGERcmd Mac agent on the Mac that is connected to the TV. TRIGGERcmd provides separate Mac downloads for Apple Silicon and Intel.

Use the Intel Mac agent on your older Mac.

If Alexa is already linked to the TRIGGERcmd account, keep using that same
TRIGGERcmd account on the TV Mac. Do not create a second TRIGGERcmd account
unless you also want to unlink and relink the Alexa skill.

For the old Intel Mac handoff, follow:

```text
docs/move-to-old-intel-mac.md
```

Create commands matching the examples in:

```text
triggercmd/commands.example.json
```

Suggested first commands:

| Alexa phrase idea | Local command |
| --- | --- |
| turn on Safari pause | `$HOME/.local/bin/safari-remote pause` |
| turn on Safari play | `$HOME/.local/bin/safari-remote play` |
| turn on Safari rewind ten | `$HOME/.local/bin/safari-remote back 10` |
| turn on Safari forward ten | `$HOME/.local/bin/safari-remote forward 10` |
| turn on Safari fullscreen | `$HOME/.local/bin/safari-remote fullscreen` |
| turn on Safari exit fullscreen | `$HOME/.local/bin/safari-remote escape` |

The TRIGGERcmd Smart Home Alexa skill generally uses phrasing like:

```text
Alexa, turn on Safari pause
```

That phrasing is not beautiful, but it is the fastest reliable bridge.

## Custom Alexa Skill

The custom skill scaffold lives in:

```text
alexa-skill/
```

It includes:

- an Alexa interaction model using invocation name `tv remote`
- a Lambda handler that parses play/pause/seek commands
- an AWS SQS bridge path for the no-rate-limit setup
- the older HTTPS bridge contract: `POST { "action": "seek", "seconds": 754 }`

Important: Alexa custom skill code runs in the cloud. It cannot directly execute commands on your Mac unless we provide a bridge. The cleanest bridge choices are:

1. AWS Lambda + SQS, with this Mac polling the queue
2. TRIGGERcmd API or bookmark URL
3. a hosted relay that the Mac polls
4. a secure tunnel or VPN endpoint

For the AWS bridge setup, follow:

```text
docs/aws-sqs-bridge-current-mac-setup.md
```

For the newer Mac / iPhone Mirroring handoff, follow:

```text
docs/newer-mac-alexa-handoff.md
```

## Project Terms

See `CONTEXT.md` for the domain terms, and `docs/adr/` for the current architecture decision.
