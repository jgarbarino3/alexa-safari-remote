# 0002: Use AWS SQS For The Custom Alexa Skill Bridge

## Status

Accepted

## Context

TRIGGERcmd proves the end-to-end path, but its free plan rate limit can be too
slow for TV controls like play, pause, and skip. The user is willing to keep a
small agent running on the TV Mac, but does not want browser windows, router port
forwarding, or an always-open tunnel.

## Decision

Use an Alexa custom skill backed by AWS Lambda. Lambda writes normalized media
actions to SQS. A lightweight LaunchAgent on the TV Mac long-polls the queue and
runs `safari-remote`.

```text
Alexa custom skill -> Lambda -> SQS -> Mac LaunchAgent -> safari-remote -> Safari
```

## Consequences

Normal personal use should fit inside AWS Lambda and SQS free tiers. The TV Mac
needs AWS CLI credentials for a dedicated least-privilege profile that can only
receive/delete messages from the queue. The setup still requires Alexa skill
enablement and optional routine creation in the Alexa app.
