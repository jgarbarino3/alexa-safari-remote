# Custom Alexa Skill Scaffold

This folder is the phase-two custom skill path. It lets Alexa understand phrases like:

- "Alexa, ask TV remote to pause"
- "Alexa, ask TV remote to rewind ten seconds"
- "Alexa, ask TV remote to go to twelve minutes thirty seconds"

## Important Constraint

Alexa custom skill code runs in the cloud. It cannot directly execute a command on your Mac unless there is a bridge.

Supported bridge choices:

1. TRIGGERcmd REST/bookmark/API bridge
2. A small HTTPS relay service that the Mac polls
3. A secure tunnel or VPN endpoint that reaches a local Mac service

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

## Files

- `interaction-model/en-US.json`: Alexa interaction model
- `lambda/index.js`: Lambda handler
- `lambda/package.json`: Lambda package metadata
