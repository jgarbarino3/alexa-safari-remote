# Context

## Glossary

### Local Controller

The macOS command-line script that turns a normalized media action into Safari video control.

### Bridge

The service that invokes the Local Controller from a voice command. TRIGGERcmd is the first Bridge; a custom Alexa skill can be a later Bridge.

### Media Action

A stable command understood by the Local Controller: `play`, `pause`, `toggle`, `back`, `forward`, `seek`, `fullscreen`, or `escape`.

### Exact Seek

Jumping to an absolute timestamp in the current video, such as `12:34`. Exact Seek requires Safari page JavaScript access to the HTML5 video element.

### Keyboard Fallback

The less precise control path that sends Safari keystrokes when page-level video control is unavailable.

### Codex Task

An arbitrary user prompt sent from Alexa to Codex on the TV Mac. Codex Tasks are separate from Media Actions because they can ask Codex to use tools, browse, or work in a repository.

### Armed Codex Session

A short-lived state where the TV Mac has opened Codex and will accept one or more Codex Tasks. The user enters this state by saying the open-Codex voice command first.
