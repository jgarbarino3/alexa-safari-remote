#!/usr/bin/env python3

from pathlib import Path
import importlib.util
import json
import tempfile
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


if __name__ == "__main__":
    unittest.main()
