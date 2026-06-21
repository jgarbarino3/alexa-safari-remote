#!/usr/bin/env python3

from pathlib import Path
import importlib.util
import json
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / "lib" / "aws-sqs-agent.py"

spec = importlib.util.spec_from_file_location("aws_sqs_agent", AGENT_PATH)
agent = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(agent)


class CommandMappingTest(unittest.TestCase):
    def setUp(self):
        self.remote = Path("/tmp/safari-remote")

    def test_simple_actions(self):
        for action in ["play", "pause", "toggle", "fullscreen", "escape"]:
            self.assertEqual(
                agent.command_for_message({"action": action}, self.remote),
                ["/tmp/safari-remote", action],
            )

    def test_relative_actions(self):
        self.assertEqual(
            agent.command_for_message({"action": "back", "seconds": 30}, self.remote),
            ["/tmp/safari-remote", "back", "30"],
        )
        self.assertEqual(
            agent.command_for_message({"action": "forward"}, self.remote),
            ["/tmp/safari-remote", "forward", "10"],
        )

    def test_seek_requires_seconds(self):
        self.assertEqual(
            agent.command_for_message({"action": "seek", "seconds": 754}, self.remote),
            ["/tmp/safari-remote", "seek", "754"],
        )
        with self.assertRaises(agent.AgentError):
            agent.command_for_message({"action": "seek"}, self.remote)

    def test_rejects_unknown_and_negative_values(self):
        with self.assertRaises(agent.AgentError):
            agent.command_for_message({"action": "reboot"}, self.remote)
        with self.assertRaises(agent.AgentError):
            agent.command_for_message({"action": "back", "seconds": -1}, self.remote)


class AgentProcessingTest(unittest.TestCase):
    def test_deletes_message_after_failed_local_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote = Path(tmp) / "safari-remote"
            remote.write_text("#!/usr/bin/env bash\nexit 7\n", encoding="utf-8")
            remote.chmod(0o755)

            class FakeAgent(agent.SqsAgent):
                def __init__(self):
                    super().__init__(
                        {
                            "QUEUE_URL": "https://example.invalid/queue",
                            "SAFARI_REMOTE_PATH": str(remote),
                            "AGENT_LOG_FILE": str(Path(tmp) / "agent.log"),
                        }
                    )
                    self.deleted = []

                def receive_message(self):
                    return {
                        "MessageId": "message-1",
                        "ReceiptHandle": "receipt-1",
                        "Body": json.dumps({"action": "escape"}),
                    }

                def delete_message(self, receipt_handle):
                    self.deleted.append(receipt_handle)

            fake = FakeAgent()
            self.assertEqual(fake.run_once(), 7)
            self.assertEqual(fake.deleted, ["receipt-1"])

            log_text = (Path(tmp) / "agent.log").read_text(encoding="utf-8")
            self.assertIn("event=message_deleted", log_text)

    def test_codex_open_arms_prompt_intake(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex = root / "codex"
            calls = root / "calls.log"
            codex.write_text(f"#!/usr/bin/env bash\necho \"$@\" >> {calls}\n", encoding="utf-8")
            codex.chmod(0o755)

            sqs_agent = agent.SqsAgent(
                {
                    "QUEUE_URL": "https://example.invalid/queue",
                    "CODEX_CLI_PATH": str(codex),
                    "CODEX_WORKSPACE_PATH": str(root),
                    "CODEX_STATE_DIR": str(root / "state"),
                    "AGENT_LOG_FILE": str(root / "agent.log"),
                    "CODEX_NEW_CHAT_ON_OPEN": "0",
                }
            )

            self.assertEqual(sqs_agent.handle_codex_action({"action": "open_codex"}, "message-1"), 0)
            status = json.loads((root / "state" / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "armed")
            self.assertGreater(status["armed_until"], int(time.time()))
            wait_for_path(calls)
            self.assertIn(f"app {root}", calls.read_text(encoding="utf-8"))

    def test_codex_quit_updates_closed_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            sqs_agent = agent.SqsAgent(
                {
                    "QUEUE_URL": "https://example.invalid/queue",
                    "CODEX_WORKSPACE_PATH": str(root),
                    "CODEX_STATE_DIR": str(root / "state"),
                    "AGENT_LOG_FILE": str(root / "agent.log"),
                }
            )

            self.assertIn(
                sqs_agent.handle_codex_action({"action": "codex_quit"}, "message-quit"),
                {0, 1},
            )
            status = json.loads((root / "state" / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "closed")
            log_text = (root / "agent.log").read_text(encoding="utf-8")
            self.assertIn("event=codex_quit", log_text)

    def test_codex_task_uses_workspace_prompt_lock_and_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex = root / "codex"
            calls = root / "calls.log"
            codex.write_text(
                f"#!/usr/bin/env bash\necho \"$@\" >> {calls}\nsleep 30\n",
                encoding="utf-8",
            )
            codex.chmod(0o755)

            sqs_agent = agent.SqsAgent(
                {
                    "QUEUE_URL": "https://example.invalid/queue",
                    "CODEX_CLI_PATH": str(codex),
                    "CODEX_WORKSPACE_PATH": str(root),
                    "CODEX_STATE_DIR": str(root / "state"),
                    "AGENT_LOG_FILE": str(root / "agent.log"),
                }
            )
            sqs_agent.update_codex_status({"state": "armed", "armed_until": int(time.time()) + 600})

            self.assertEqual(
                sqs_agent.handle_codex_action({"action": "codex_task", "prompt": "summarize status"}, "message-2"),
                0,
            )
            self.assertTrue((root / "state" / "task.lock").exists())
            wait_for_path(calls)
            self.assertIn(f"exec -C {root} summarize status", calls.read_text(encoding="utf-8"))
            self.assertEqual(
                sqs_agent.handle_codex_action({"action": "codex_task", "prompt": "second task"}, "message-3"),
                4,
            )
            self.assertEqual(sqs_agent.handle_codex_action({"action": "codex_cancel"}, "message-4"), 0)

    def test_browser_action_runs_worker_and_logs_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = root / "chrome-worker.py"
            worker.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "print(json.dumps({'ok': True, 'event': 'browser_opened', 'site': 'peacock'}))\n",
                encoding="utf-8",
            )
            worker.chmod(0o755)

            sqs_agent = agent.SqsAgent(
                {
                    "QUEUE_URL": "https://example.invalid/queue",
                    "BROWSER_WORKER_PATH": str(worker),
                    "CODEX_WORKSPACE_PATH": str(root),
                    "CODEX_STATE_DIR": str(root / "state"),
                    "AGENT_LOG_FILE": str(root / "agent.log"),
                }
            )

            self.assertEqual(sqs_agent.handle_browser_action({"action": "browser_open", "site": "peacock"}, "message-5"), 0)
            log_text = (root / "agent.log").read_text(encoding="utf-8")
            self.assertIn("event=browser_action_done", log_text)
            self.assertIn("worker_event=browser_opened", log_text)

    def test_live_codex_prompt_requires_armed_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqs_agent = agent.SqsAgent(
                {
                    "QUEUE_URL": "https://example.invalid/queue",
                    "CODEX_WORKSPACE_PATH": str(root),
                    "CODEX_STATE_DIR": str(root / "state"),
                    "AGENT_LOG_FILE": str(root / "agent.log"),
                }
            )

            self.assertEqual(
                sqs_agent.handle_codex_action({"action": "live_codex_prompt", "prompt": "hello"}, "message-6"),
                3,
            )
            log_text = (root / "agent.log").read_text(encoding="utf-8")
            self.assertIn("event=live_codex_rejected", log_text)
            self.assertIn("reason=not_armed", log_text)

    def test_live_codex_prompt_text_requests_chrome_fullscreen_finish(self):
        prompt = agent.live_codex_prompt_text("open peacock and play the last episode")
        self.assertIn("User voice prompt: open peacock and play the last episode", prompt)
        self.assertIn("leaving Google Chrome frontmost", prompt)
        self.assertIn("make the player fullscreen", prompt)


def wait_for_path(path: Path, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {path}")


if __name__ == "__main__":
    unittest.main()
