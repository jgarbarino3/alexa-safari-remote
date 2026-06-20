# 0001: Use a Local Controller Before Building the Custom Alexa Skill

## Status

Accepted

## Context

The user wants Alexa voice control for Safari video playback while a Mac is connected to a TV by HDMI. Streaming sites such as Peacock and Disney can expose different player UIs, and a full Alexa custom skill introduces cloud hosting, authentication, and relay choices.

## Decision

Build and prove a local macOS controller first. The controller accepts normalized media actions and controls Safari directly. TRIGGERcmd is the first bridge because it can invoke local commands from Alexa without exposing the Mac to inbound network traffic.

The future custom Alexa skill should call the same media-action contract rather than duplicating Safari-specific logic.

## Consequences

Basic commands can work quickly through TRIGGERcmd. Exact spoken timestamps remain a phase-two feature unless TRIGGERcmd parameter support is sufficient for the desired phrasing.

The custom skill still needs a bridge from Alexa cloud execution to the Mac, such as TRIGGERcmd, a secure webhook relay, or a VPN/tunnel-based local service.
