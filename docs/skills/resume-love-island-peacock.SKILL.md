---
name: resume-love-island-peacock
description: Use when the user asks to play, open, resume, or continue Love Island on Peacock in Chrome, especially voice prompts like "love island" that should choose the Lillia Peacock profile and resume Love Island USA.
---

# Resume Love Island on Peacock

Predictability matters more than speed. Use Chrome's visible UI only; do not inspect history, cookies, local storage, passwords, profile files, or other protected browser data.

## Assumptions

- This is the old Intel TV Mac on the HDMI display.
- The reusable Alexa/Codex thread should be in the `alexa-safari-remote` repo workspace, not whatever control thread is currently chatting with the user. Reuse that repo thread rather than starting a new thread unless the user explicitly asks for a new chat.
- The Mac helper should already have attempted Surfshark USA Fastest and opened Peacock. If not, do those visible steps directly.

## Workflow

1. Confirm Surfshark is routing through the United States.
   Completion: either public country code is `US`, or Surfshark visibly shows a connected United States endpoint. If it is not connected, activate Surfshark and click Quick-connect at the HDMI-calibrated point. Working values: absolute `1437,725`, Surfshark-window-relative `704,540`. Use:

   ```bash
   osascript -e 'tell application "Surfshark" to activate' -e 'delay 0.4'
   /usr/local/bin/cliclick c:1437,725
   ```

   Wait 10-20 seconds, then verify country again. If the click misses, use the visible Quick-connect button; do not proceed to Peacock while the country is not `US`.

2. Use `chrome:control-chrome`.
   Completion: browser documentation has been read, the session is named for Love Island/Peacock, and a Peacock tab has been claimed or opened.

3. Start from the user's visible Peacock state.
   Completion: use `browser.user.openTabs()` only to find open tabs. Prefer an existing Peacock search, playback, or profile tab. Do not use browser history.

4. Select the Lillia profile when Peacock shows profiles.
   Completion: the Peacock home/search UI is visible for profile Lillia, or a blocker is visible.

5. Find Love Island.
   Completion: the visible Peacock UI shows the Love Island title page. If multiple versions appear, choose Love Island USA/default Peacock "Love Island" unless the user specified another version.

6. Resume from visible progress.
   Completion: choose the strongest visible resume signal in this order:
   - Title page button like `Resume Season 8, Episode 12`.
   - Continue Watching item for Love Island.
   - Episode card with visible watch progress.
   If no resume/progress signal is visible, leave the Love Island page visible and say what is needed.

7. Start playback.
   Completion: URL or page state indicates Peacock playback, a `video` element exists, and `video.paused === false`.

8. Make the playback tab the selected front tab before fullscreen.
   Completion: `browser.tabs.selected()` returns the same tab id and playback URL as the controlled tab. If not, use visible Chrome/tab UI or `tell application "Google Chrome" to activate` plus browser tab selection to return to the playback tab. Never finalize or end on a different Peacock tab.

9. Fullscreen with Chrome presentation fullscreen.
   Completion: activate Chrome, make the playback tab selected, click the middle of the video surface once to focus the player, then send `Command+Shift+F` to Google Chrome. This was more reliable than Peacock's own fullscreen HUD. If it misses, reactivate Chrome and send `Command+Shift+F` once more. Use player `f`, double-click video, or visible fullscreen HUD only as fallbacks.

10. Final check after every focus-changing/tool action.
   Completion: all are true:
   - macOS frontmost app is `Google Chrome` via `osascript`.
   - selected Chrome tab is the playback tab, not a search/profile/title tab.
   - Love Island is visible or playing.
   - The player is actually fullscreen: take a real macOS screen screenshot and verify the Chrome tab strip/address bar are gone. Browser viewport screenshots are not enough because they do not show Chrome tabs. DRM may make the video area black; that is acceptable if the Chrome UI is gone.
   If Codex becomes frontmost during verification, activate Chrome again and re-check. If fullscreen missed, retry fullscreen once. After `browser.tabs.finalize({ keep: [{ tab, status: "handoff" }] })`, activate Google Chrome again with AppleScript and confirm Chrome is frontmost, because final responses/tool calls can bring Codex forward.

## Blockers

If login, region block, CAPTCHA, payment, age verification, or another user-only blocker appears, leave that blocker visible in Chrome and report the exact action needed. Do not work around it with web search or protected browser data.

## Useful Checks

Use page evaluation only for visible/player state:

```js
await tab.playwright.evaluate(() => ({
  title: document.title,
  url: location.href,
  hasVideo: !!document.querySelector("video"),
  videoPaused: document.querySelector("video")?.paused ?? null,
  currentTime: document.querySelector("video")?.currentTime ?? null,
  fullscreen: !!document.fullscreenElement,
  visibleText: document.body.innerText.slice(0, 250),
}));
```

Use AppleScript only for app focus:

```bash
osascript -e 'tell application "Google Chrome" to activate'
osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true'
```

Use a real screen capture for fullscreen verification:

```bash
screencapture -x /tmp/love-island-fullscreen.png
```
