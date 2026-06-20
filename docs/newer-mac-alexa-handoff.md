# Newer Mac Alexa App Handoff

Use this on the newer Mac with iPhone Mirroring after the TV Mac has completed:

```text
docs/aws-sqs-bridge-current-mac-setup.md
```

The TV Mac does the actual Safari control. The newer Mac only helps finish the
Alexa app / phone setup.

## Codex Prompt For The Newer Mac

Paste this into Codex on the newer Mac:

```text
Use https://github.com/jgarbarino3/alexa-safari-remote on branch
feature/aws-sqs-bridge. Read docs/newer-mac-alexa-handoff.md and help me use
iPhone Mirroring to enable the Alexa custom skill and create short Alexa
routines for the Safari remote commands. Do not ask for or print AWS keys,
TRIGGERcmd tokens, passwords, or private account data.
```

## Skill Setup Data

The custom skill package lives here:

```text
alexa-skill/skill-package/
```

If the skill has not been deployed yet, install and authenticate the ASK CLI:

```bash
npm install -g ask-cli
ask configure
```

Then deploy from the repo:

```bash
./scripts/deploy-alexa-skill.sh
```

Invocation name:

```text
tv remote
```

The current TV Mac setup has already deployed the development skill when
`alexa-skill/.ask/ask-states.json` exists on that Mac. Do not copy that file
into Git; it is local account state.

## Enable And Test The Skill

1. Open iPhone Mirroring on the newer Mac.
2. Open the Alexa app on the mirrored iPhone.
3. Find the development skill named for this project, or open it from the Alexa
   Developer Console flow if it is not visible in the app yet.
4. Enable the skill on the same Amazon/Alexa account used by the Echo device.
5. Test:

```text
Alexa, ask tv remote to pause
Alexa, ask tv remote to play
Alexa, ask tv remote to rewind ten seconds
Alexa, ask tv remote to skip forward thirty seconds
Alexa, ask tv remote to fullscreen
Alexa, ask tv remote to exit fullscreen
```

While testing, watch this file on the TV Mac:

```bash
tail -f ~/.local/state/alexa-safari-remote/commands.log
```

## Optional Short Routines

If you want shorter phrasing, create Alexa routines that map friendly phrases to
custom skill actions. Suggested phrases:

| Routine phrase | Custom skill action |
| --- | --- |
| `safari pause` or `turn on safari pause` | `ask tv remote to pause` |
| `safari play` or `turn on safari play` | `ask tv remote to play` |
| `safari rewind ten` or `turn on safari rewind ten` | `ask tv remote to rewind ten seconds` |
| `safari forward ten` or `turn on safari forward ten` | `ask tv remote to skip forward ten seconds` |
| `safari rewind thirty` or `turn on safari rewind thirty` | `ask tv remote to rewind thirty seconds` |
| `safari forward thirty` or `turn on safari forward thirty` | `ask tv remote to skip forward thirty seconds` |
| `safari fullscreen` or `turn on safari fullscreen` | `ask tv remote to fullscreen` |
| `safari exit fullscreen` or `turn on safari exit fullscreen` | `ask tv remote to exit fullscreen` |

The exact Alexa app screen names can vary. If a routine action cannot directly
call a custom skill on the current app version, keep the custom skill phrase as
the fallback.
