import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="bonfyre-action-")
        self.addCleanup(self.directory.cleanup)
        self.work = Path(self.directory.name).resolve()
        self.receipt = self.work / "receipt with spaces.json"
        self.output = self.work / "github-output"
        self.script = textwrap.dedent(
            (ROOT / "action.yml").read_text().split("      run: |\n", 1)[1]
        )

    def run_action(self, trace):
        self.output.write_text("")
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", self.script],
            env={**os.environ, "GITHUB_ACTION_PATH": str(ROOT),
                 "BONFYRE_TRACE_PATH": str(trace),
                 "BONFYRE_RECEIPT_PATH": str(self.receipt),
                 "GITHUB_OUTPUT": str(self.output)},
            cwd=self.work, capture_output=True, text=True, timeout=10,
        )
        outputs = dict(line.split("=", 1) for line in self.output.read_text().splitlines())
        return result, outputs

    def seed_success(self):
        result, outputs = self.run_action(ROOT / "examples/pass.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(outputs["passed"], "true")
        self.assertEqual(outputs["receipt-path"], str(self.receipt))
        return self.receipt.read_text()

    def test_malformed_retry_does_not_publish_previous_success(self):
        previous = self.seed_success()
        bad = self.work / "malformed.json"
        bad.write_text("{")
        result, outputs = self.run_action(bad)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(outputs, {"passed": "false", "receipt-id": "",
                                  "trace-digest": "", "receipt-path": ""})
        self.assertNotIn(json.loads(previous)["receipt_id"], result.stdout)

    def test_missing_trace_does_not_publish_previous_success(self):
        self.seed_success()
        result, outputs = self.run_action(self.work / "missing.json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(outputs["passed"], "false")
        self.assertEqual(outputs["receipt-path"], "")
        self.assertEqual(outputs["receipt-id"], "")

    def test_policy_failure_publishes_its_own_receipt(self):
        previous = json.loads(self.seed_success())
        result, outputs = self.run_action(ROOT / "examples/fail.json")
        self.assertEqual(result.returncode, 1, result.stderr)
        receipt = json.loads(self.receipt.read_text())
        self.assertFalse(receipt["passed"])
        self.assertEqual(outputs["passed"], "false")
        self.assertEqual(outputs["receipt-id"], receipt["receipt_id"])
        self.assertNotEqual(receipt["receipt_id"], previous["receipt_id"])

    def test_unwritable_destination_cannot_publish_success(self):
        self.receipt = self.work / "missing-parent" / "receipt.json"
        result, outputs = self.run_action(ROOT / "examples/pass.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(outputs.get("passed"), "true")
        self.assertFalse(self.receipt.exists())


if __name__ == "__main__":
    unittest.main()
