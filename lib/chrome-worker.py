#!/usr/bin/env python3
"""Local Chrome worker for Alexa TV/browser actions.

This worker intentionally avoids Codex MCP. It uses local macOS commands that
can run from the LaunchAgent context and logs clear success/failure events.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote_plus


SITE_URLS = {
    "peacock": "https://www.peacocktv.com/",
    "peacock tv": "https://www.peacocktv.com/",
    "disney": "https://www.disneyplus.com/",
    "disney plus": "https://www.disneyplus.com/",
    "netflix": "https://www.netflix.com/",
    "youtube": "https://www.youtube.com/",
    "you tube": "https://www.youtube.com/",
    "hulu": "https://www.hulu.com/",
    "prime": "https://www.primevideo.com/",
    "prime video": "https://www.primevideo.com/",
}

SEARCH_URLS = {
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "you tube": "https://www.youtube.com/results?search_query={query}",
    "netflix": "https://www.netflix.com/search?q={query}",
    "disney": "https://www.disneyplus.com/search/{query}",
    "disney plus": "https://www.disneyplus.com/search/{query}",
    "peacock": "https://www.peacocktv.com/search?q={query}",
    "peacock tv": "https://www.peacocktv.com/search?q={query}",
    "hulu": "https://www.hulu.com/search?q={query}",
    "prime": "https://www.primevideo.com/search/ref=atv_nb_sr?phrase={query}",
    "prime video": "https://www.primevideo.com/search/ref=atv_nb_sr?phrase={query}",
}

KEY_COMMANDS = {
    "play": ["space"],
    "pause": ["space"],
    "toggle": ["space"],
    "fullscreen": ["f"],
    "escape": ["escape"],
}


class WorkerError(Exception):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local Chrome TV/browser action.")
    parser.add_argument("--message", required=True, help="JSON message body")
    args = parser.parse_args()

    message = json.loads(args.message)
    result = run_action(message)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else int(result.get("returncode") or 1)


def run_action(message: dict[str, object]) -> dict[str, object]:
    action = normalized(message.get("action"))
    try:
        if action == "browser_open":
            return open_site(str(message.get("site") or message.get("url") or ""))
        if action == "browser_search":
            return search_site(str(message.get("site") or ""), str(message.get("query") or ""))
        if action == "browser_command":
            return browser_command(str(message.get("command") or ""))
        if action == "browser_seek":
            return seek(int(message.get("seconds") or 0))
        if action == "browser_status":
            return status()
        raise WorkerError(f"unsupported action: {action}")
    except Exception as error:
        return {"ok": False, "event": "browser_error", "error": str(error)}


def open_site(site_or_url: str) -> dict[str, object]:
    target = site_or_url.strip()
    if not target:
        raise WorkerError("missing site")
    url = site_to_url(target)
    open_chrome_url(url)
    return {"ok": True, "event": "browser_opened", "url": safe_url(url)}


def search_site(site: str, query: str) -> dict[str, object]:
    site_key = normalized(site)
    clean_query = query.strip()
    if not site_key:
        raise WorkerError("missing site")
    if not clean_query:
        raise WorkerError("missing query")
    template = SEARCH_URLS.get(site_key)
    if not template:
        template = "https://www.google.com/search?q=site%3A{site}+{query}".format(
            site=quote_plus(site_key),
            query="{query}",
        )
    url = template.format(query=quote_plus(clean_query))
    open_chrome_url(url)
    return {"ok": True, "event": "browser_search_opened", "site": site_key, "query": clean_query}


def browser_command(command: str) -> dict[str, object]:
    command_key = normalized(command)
    if command_key in {"play pause", "play/pause"}:
        command_key = "toggle"
    keys = KEY_COMMANDS.get(command_key)
    if not keys:
        raise WorkerError(f"unsupported browser command: {command}")
    for key in keys:
        system_events_key(key)
    return {"ok": True, "event": "browser_command_sent", "command": command_key}


def seek(seconds: int) -> dict[str, object]:
    if seconds == 0:
        raise WorkerError("missing seconds")
    key = "l" if seconds > 0 else "j"
    presses = max(1, min(abs(seconds) // 10, 18))
    for _ in range(presses):
        system_events_key(key)
    return {"ok": True, "event": "browser_seek_sent", "seconds": seconds, "keypresses": presses}


def status() -> dict[str, object]:
    completed = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'],
        text=True,
        capture_output=True,
        check=False,
    )
    front_app = completed.stdout.strip() if completed.returncode == 0 else "unknown"
    return {"ok": True, "event": "browser_status", "front_app": front_app}


def site_to_url(value: str) -> str:
    key = normalized(value)
    if key in SITE_URLS:
        return SITE_URLS[key]
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if "." in value and " " not in value:
        return f"https://{value}"
    return f"https://www.google.com/search?q={quote_plus(value)}"


def open_chrome_url(url: str) -> None:
    completed = subprocess.run(["open", "-a", "Google Chrome", url], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise WorkerError(completed.stderr.strip() or f"open exited {completed.returncode}")


def system_events_key(key: str) -> None:
    script = [
        'tell application "Google Chrome" to activate',
        "delay 0.15",
        'tell application "System Events"',
    ]
    if key == "space":
        script.append("key code 49")
    elif key == "escape":
        script.append("key code 53")
    else:
        script.append(f'keystroke "{key}"')
    script.append("end tell")
    completed = subprocess.run(["osascript", *sum([["-e", line] for line in script], [])], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise WorkerError(completed.stderr.strip() or f"osascript exited {completed.returncode}")


def normalized(value: object) -> str:
    return str(value or "").strip().lower()


def safe_url(url: str) -> str:
    # Avoid logging query strings that may contain spoken private data.
    return url.split("?", 1)[0]


if __name__ == "__main__":
    sys.exit(main())
