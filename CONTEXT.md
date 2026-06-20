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
