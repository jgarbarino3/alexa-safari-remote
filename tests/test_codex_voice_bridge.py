#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "lib" / "codex_voice_bridge.py"


class CodexVoiceBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.fake_bin = self.root / "bin"
        self.fake_bin.mkdir()
        self.fake_codex = self.fake_bin / "codex"
        self.fake_codex.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "echo \"$*\" >> \"$FAKE_CODEX_LOG\"\n"
            "if [[ \"${FAKE_CODEX_FAIL:-}\" == \"1\" ]]; then exit 7; fi\n"
            "if [[ \"${FAKE_CODEX_SLEEP:-}\" != \"\" ]]; then sleep \"$FAKE_CODEX_SLEEP\"; fi\n"
            "echo \"fake codex ok\"\n",
            encoding="utf-8",
        )
        self.fake_codex.chmod(0o755)
        self.env = os.environ.copy()
        self.env.update(
            {
                "ALEXA_CODEX_STATE_DIR": str(self.root / "state"),
                "ALEXA_CODEX_WORKSPACE": str(self.workspace),
                "ALEXA_CODEX_BIN": str(self.fake_codex),
                "FAKE_CODEX_LOG": str(self.root / "codex.log"),
            }
        )

    def tearDown(self):
        self.tmp.cleanup()

    def run_bridge(self, *args, **extra_env):
        env = self.env.copy()
        env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(BRIDGE), *args],
            text=True,
            capture_output=True,
            env=env,
        )

    def test_open_arms_codex(self):
        result = self.run_bridge("open", "--arm-seconds", "30")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK:open_codex:armed:30", result.stdout)
        self.assertIn(f"app {self.workspace.resolve()}", (self.root / "codex.log").read_text(encoding="utf-8"))

    def test_ask_requires_open_codex_first(self):
        result = self.run_bridge("ask", "open", "example")

        self.assertEqual(result.returncode, 2)
        self.assertIn("Codex is not armed", result.stderr)

    def test_ask_runs_codex_exec_after_open(self):
        self.assertEqual(self.run_bridge("open").returncode, 0)

        result = self.run_bridge("ask", "open", "example", "dot", "com")

        self.assertEqual(result.returncode, 0, result.stderr)
        log = (self.root / "codex.log").read_text(encoding="utf-8")
        self.assertIn("exec -C", log)
        self.assertIn("open example dot com", log)
        status = json.loads(self.run_bridge("status").stdout)
        self.assertEqual(status["status"], "ok")
        self.assertTrue(status["armed"])

    def test_failed_task_is_recorded_and_not_left_running(self):
        self.assertEqual(self.run_bridge("open").returncode, 0)

        result = self.run_bridge("ask", "fail", FAKE_CODEX_FAIL="1")

        self.assertEqual(result.returncode, 2)
        status = json.loads(self.run_bridge("status").stdout)
        self.assertEqual(status["status"], "failed")
        self.assertIsNone(status["running_pid"])
        self.assertFalse((self.root / "state" / "codex-task.lock").exists())

    def test_cancel_disarms_codex(self):
        self.assertEqual(self.run_bridge("open").returncode, 0)

        result = self.run_bridge("cancel")

        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(self.run_bridge("status").stdout)
        self.assertFalse(status["armed"])
        self.assertEqual(status["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
