#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DISPATCH = REPO / "lib" / "bridge_dispatch.py"


class BridgeDispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = os.environ.copy()
        self.env.update(
            {
                "SAFARI_REMOTE_BIN": "/tmp/fake-safari-remote",
                "CODEX_VOICE_BRIDGE_BIN": "/tmp/fake-codex-voice-bridge",
            }
        )

    def tearDown(self):
        self.tmp.cleanup()

    def dry_run(self, payload):
        action_file = self.root / "action.json"
        action_file.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(DISPATCH), "--dry-run", str(action_file)],
            text=True,
            capture_output=True,
            env=self.env,
        )

    def test_dispatches_media_action(self):
        result = self.dry_run({"action": "forward", "seconds": 30})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["/tmp/fake-safari-remote", "forward", "30"])

    def test_dispatches_codex_open(self):
        result = self.dry_run({"action": "open_codex"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["/tmp/fake-codex-voice-bridge", "open"])

    def test_dispatches_codex_task(self):
        result = self.dry_run({"action": "codex_task", "prompt": "open peacock"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["/tmp/fake-codex-voice-bridge", "ask", "open peacock"])

    def test_rejects_codex_task_without_prompt(self):
        result = self.dry_run({"action": "codex_task"})

        self.assertEqual(result.returncode, 2)
        self.assertIn("requires prompt", result.stderr)


if __name__ == "__main__":
    unittest.main()
