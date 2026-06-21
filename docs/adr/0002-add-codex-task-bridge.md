# 0002: Add Codex Tasks As A Separate Bridge Command Family

## Status

Accepted

## Context

The Safari remote controls a small set of normalized media actions. The user now
wants Alexa to open Codex on the TV Mac and send arbitrary prompts, such as
asking Codex to use browser tooling to open a streaming site.

`codex app` launches Codex Desktop but does not expose a documented way to send
a prompt into an already-open visible chat. `codex exec` does accept a prompt and
keeps Codex's normal sandbox and approval behavior.

## Decision

Keep Media Actions and Codex Tasks separate. Alexa can send `open_codex` to make
Codex visible and arm prompt intake, then send `codex_task` messages that the Mac
runs through `codex exec`.

## Consequences

The bridge stays simple and does not need UI automation. Codex remains the safety
boundary for arbitrary prompts. The visible Desktop app is an arming/presence
signal, not the prompt transport.
