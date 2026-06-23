# Agent Instructions

- For requests to open, play, resume, or continue Love Island on Peacock, including short voice prompts like "love island", always use the `resume-love-island-peacock` skill.
- That flow must use Google Chrome and Peacock's visible UI only, select the Lillia profile when needed, prefer the visible resume/Continue Watching signal, and finish with Chrome frontmost on the actual Love Island playback tab in fullscreen. Prefer keyboard/video-surface fullscreen or Chrome presentation fullscreen over chasing Peacock's disappearing HUD, and verify with a real macOS screen capture that the Chrome tab strip/address bar are gone.
- For Surfshark native UI control, first rely on the Mac helper's built-in Quick-connect automation. If live Codex intervention is needed, prefer the configured `macos-mcp` screenshot/Accessibility path over raw screenshot-pixel clicks; if falling back to `cliclick`, use macOS point coordinates and activate Surfshark immediately before clicking.
- A repo copy of the Love Island skill is kept at `docs/skills/resume-love-island-peacock.SKILL.md`; the installed local skill at `~/.codex/skills/resume-love-island-peacock/SKILL.md` should match it.
