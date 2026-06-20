# Custom Alexa Skill Scaffold

This folder is the phase-two custom skill path. It lets Alexa understand phrases like:

- "Alexa, ask TV remote to pause"
- "Alexa, ask TV remote to rewind ten seconds"
- "Alexa, ask TV remote to go to twelve minutes thirty seconds"

## Important Constraint

Alexa custom skill code runs in the cloud. It cannot directly execute a command on your Mac unless there is a bridge.

Supported bridge choices:

1. AWS Lambda + SQS, with the Mac polling the queue
2. TRIGGERcmd REST/bookmark/API bridge
3. A small HTTPS relay service that the Mac polls
4. A secure tunnel or VPN endpoint that reaches a local Mac service

The preferred free bridge is AWS SQS:

```text
Alexa custom skill -> Lambda -> SQS -> Mac LaunchAgent -> safari-remote
```

Set the Lambda environment variable:

```text
ALEXA_SAFARI_REMOTE_QUEUE_URL=<SQS queue URL>
```

When that variable is present, the Lambda writes each normalized media action to
SQS. The Mac agent consumes those messages and runs `safari-remote`.

The Lambda scaffold calls `REMOTE_ENDPOINT_URL` with a JSON body:

```json
{
  "action": "seek",
  "seconds": 750
}
```

The endpoint should translate that request into:

```bash
safari-remote seek 12:30
```

## Environment Variables

- `REMOTE_ENDPOINT_URL`: HTTPS endpoint for the bridge
- `REMOTE_ENDPOINT_TOKEN`: optional bearer token sent as `Authorization: Bearer ...`
- `ALEXA_SAFARI_REMOTE_QUEUE_URL`: SQS queue URL for the preferred AWS bridge

## Files

- `interaction-model/en-US.json`: Alexa interaction model
- `lambda/index.js`: Lambda handler
- `lambda/package.json`: Lambda package metadata

## Setup Docs

- `../docs/aws-sqs-bridge-current-mac-setup.md`
- `../docs/newer-mac-alexa-handoff.md`
