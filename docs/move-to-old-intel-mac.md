# Move The Alexa Setup To The Old Intel Mac

Use this when the Alexa skill is already linked to the TRIGGERcmd account and
the old Intel Mac will be the Mac connected to the TV by HDMI.

## Intended Account Layout

Use one TRIGGERcmd account:

```text
Alexa app -> TRIGGERcmd Smart Home skill -> same TRIGGERcmd account -> old Intel Mac
```

Do not create a second TRIGGERcmd account for the old Mac unless you also want
to unlink and relink the Alexa skill in the Alexa app.

If the TRIGGERcmd account only allows one computer, delete or disconnect the
temporary setup Mac from the TRIGGERcmd website before registering the old Mac.
The Alexa skill link can remain in place.

## Install The Local Safari Remote

On the old Intel Mac:

```bash
git clone https://github.com/jgarbarino3/alexa-safari-remote.git
cd alexa-safari-remote
./install.sh
```

Then run:

```bash
~/.local/bin/safari-remote selftest
```

Expected output:

```text
OK:selftest
```

## Approve Safari Control

In Safari on the old Mac:

1. Open Safari > Settings > Advanced, or Safari > Preferences > Advanced on
   older macOS versions.
2. Enable the developer menu if it is not already visible.
3. Open the Develop menu.
4. Enable Allow JavaScript from Apple Events.

This is the setting that lets the command control the actual HTML5 video
element instead of guessing where a streaming site's buttons are.

## Approve Accessibility And Automation

Run:

```bash
~/.local/bin/safari-remote-prime-permissions
```

Approve any macOS prompts. If macOS does not show a prompt, open:

```text
System Settings > Privacy & Security > Accessibility
```

On older macOS versions, this may be:

```text
System Preferences > Security & Privacy > Privacy > Accessibility
```

Allow Terminal while testing. After TRIGGERcmd is installed, allow
TRIGGERcmdAgent as well.

## Install The Intel TRIGGERcmd Agent

Download the Intel Mac agent from TRIGGERcmd:

```text
https://agents.triggercmd.com/TRIGGERcmdAgent-x64.dmg
```

Install and launch `TRIGGERcmdAgent.app`.

Sign in with the same TRIGGERcmd account that is already linked to the Alexa
app. Use a computer name like:

```text
Safari TV Mac
```

## Add The Safari Commands

Add commands matching:

```text
triggercmd/commands.example.json
```

The core commands should point to:

```text
$HOME/.local/bin/safari-remote pause
$HOME/.local/bin/safari-remote play
$HOME/.local/bin/safari-remote back 10
$HOME/.local/bin/safari-remote forward 10
$HOME/.local/bin/safari-remote back 30
$HOME/.local/bin/safari-remote forward 30
$HOME/.local/bin/safari-remote fullscreen
$HOME/.local/bin/safari-remote escape
```

Set them to foreground commands.

## Refresh Alexa

In the Alexa app:

1. Open Devices.
2. Run device discovery if the Safari command devices are not visible.
3. Keep the command names simple: `safari pause`, `safari play`,
   `safari rewind ten`, `safari forward ten`, and so on.

Use phrases like:

```text
Alexa, turn on safari pause
Alexa, turn on safari play
Alexa, turn on safari rewind ten
Alexa, turn on safari forward ten
Alexa, turn on safari fullscreen
Alexa, turn on safari exit fullscreen
```

## Verify End To End

Open a Safari video on the old Mac, then say:

```text
Alexa, turn on safari pause
```

Check the local command log:

```bash
tail -n 20 ~/.local/state/alexa-safari-remote/commands.log
```

You should see a recent line like:

```text
2026-06-20T18:50:00Z action=pause args=pause
```

If the log updates but the video does not respond, re-check Safari's
JavaScript-from-Apple-Events setting and the Accessibility permission for
TRIGGERcmdAgent.

## Copy-Paste Prompt For Codex On The Old Mac

Paste this into Codex on the old Intel Mac:

```text
Please set up https://github.com/jgarbarino3/alexa-safari-remote on this Mac.
This is the Intel Mac that will be connected to the TV by HDMI. The Alexa app
is already linked to the correct TRIGGERcmd account, so use that same
TRIGGERcmd account and do not create a second account.

Install the repo, run ./install.sh, help me approve Safari JavaScript from
Apple Events and Accessibility/Automation permissions, install the Intel
TRIGGERcmd agent, add the commands from triggercmd/commands.example.json, and
verify with safari-remote selftest plus ~/.local/state/alexa-safari-remote/commands.log.
Do not commit or print any TRIGGERcmd token or private account data.
```
