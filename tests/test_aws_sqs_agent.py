#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
AGENT = REPO / "lib" / "aws_sqs_agent.py"


class AwsSqsAgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.aws_log = self.root / "aws.log"
        self.dispatch_log = self.root / "dispatch.log"
        self.fake_aws = self.bin / "aws"
        self.fake_dispatch = self.bin / "dispatch"
        self.fake_aws.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "echo \"$*\" >> \"$AWS_LOG\"\n"
            "if [[ \"$1 $2\" == \"sqs receive-message\" ]]; then\n"
            "  printf '%s\\n' \"$AWS_RECEIVE_JSON\"\n"
            "elif [[ \"$1 $2\" == \"sqs delete-message\" ]]; then\n"
            "  exit 0\n"
            "else\n"
            "  exit 2\n"
            "fi\n",
            encoding="utf-8",
        )
        self.fake_dispatch.write_text(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            "body = sys.stdin.read()\n"
            "open(os.environ['DISPATCH_LOG'], 'a').write(body + '\\n')\n"
            "sys.exit(int(os.environ.get('DISPATCH_RC', '0')))\n",
            encoding="utf-8",
        )
        self.fake_aws.chmod(0o755)
        self.fake_dispatch.chmod(0o755)
        self.env = os.environ.copy()
        self.env.update(
            {
                "AWS_BIN": str(self.fake_aws),
                "AWS_LOG": str(self.aws_log),
                "ALEXA_BRIDGE_DISPATCH_BIN": str(self.fake_dispatch),
                "DISPATCH_LOG": str(self.dispatch_log),
                "ALEXA_SQS_QUEUE_URL": "https://sqs.example.test/queue",
                "ALEXA_SQS_AGENT_LOG": str(self.root / "agent.log"),
            }
        )

    def tearDown(self):
        self.tmp.cleanup()

    def run_agent(self, receive_json, **extra_env):
        env = self.env.copy()
        env.update(extra_env)
        env["AWS_RECEIVE_JSON"] = json.dumps(receive_json)
        return subprocess.run(
            [sys.executable, str(AGENT), "--once"],
            text=True,
            capture_output=True,
            env=env,
        )

    def test_dispatches_and_deletes_successful_message(self):
        result = self.run_agent(
            {
                "Messages": [
                    {
                        "MessageId": "m1",
                        "ReceiptHandle": "rh1",
                        "Body": json.dumps({"action": "open_codex"}),
                    }
                ]
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.dispatch_log.read_text(encoding="utf-8")), {"action": "open_codex"})
        self.assertIn("delete-message", self.aws_log.read_text(encoding="utf-8"))

    def test_deletes_failed_dispatch_by_default_to_avoid_poison_loop(self):
        result = self.run_agent(
            {
                "Messages": [
                    {
                        "MessageId": "m2",
                        "ReceiptHandle": "rh2",
                        "Body": json.dumps({"action": "codex_task", "prompt": "fail"}),
                    }
                ]
            },
            DISPATCH_RC="9",
        )

        self.assertEqual(result.returncode, 9)
        self.assertIn("delete-message", self.aws_log.read_text(encoding="utf-8"))
        self.assertIn("message_deleted", (self.root / "agent.log").read_text(encoding="utf-8"))

    def test_empty_poll_succeeds(self):
        result = self.run_agent({})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("poll_empty", (self.root / "agent.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
