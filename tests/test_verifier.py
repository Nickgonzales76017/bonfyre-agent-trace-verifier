import copy
import json
import unittest
from pathlib import Path

from verifier import InputError, verify

ROOT = Path(__file__).resolve().parents[1]


class VerifierTests(unittest.TestCase):
    def load(self, name):
        return json.loads((ROOT / "examples" / name).read_text())

    def test_safe_trace_passes_deterministically(self):
        trace = self.load("pass.json")
        first = verify(trace)
        second = verify(copy.deepcopy(trace))
        self.assertTrue(first["passed"])
        self.assertEqual(first, second)
        self.assertEqual(set(first["dimensions"]), {
            "task_success", "semantic_consistency", "effect_safety",
            "authority_compliance", "evidence_sufficiency",
            "recovery_quality", "trajectory_efficiency", "cost"
        })

    def test_unsafe_trace_fails_separate_dimensions(self):
        result = verify(self.load("fail.json"))
        self.assertFalse(result["passed"])
        self.assertFalse(result["dimensions"]["task_success"]["passed"])
        self.assertFalse(result["dimensions"]["effect_safety"]["passed"])
        self.assertFalse(result["dimensions"]["authority_compliance"]["passed"])
        self.assertFalse(result["dimensions"]["evidence_sufficiency"]["passed"])
        self.assertFalse(result["dimensions"]["cost"]["passed"])

    def test_failed_mutation_requires_compensation(self):
        trace = self.load("pass.json")
        trace["events"][1]["status"] = "failed"
        result = verify(trace)
        self.assertFalse(result["dimensions"]["recovery_quality"]["passed"])
        trace["events"].append({
            "event_id": "evt-4", "actor": "support-agent", "action": "restore_ticket",
            "resource": "ticket:HD-1042", "effect": "write", "authority": "ticket:write",
            "status": "succeeded", "evidence": ["receipt:restore-1"], "compensates": "evt-2"
        })
        trace["task"]["max_steps"] = 4
        self.assertTrue(verify(trace)["dimensions"]["recovery_quality"]["passed"])

    def test_missing_trace_id_is_input_error(self):
        trace = self.load("pass.json")
        del trace["trace_id"]
        with self.assertRaises(InputError):
            verify(trace)


if __name__ == "__main__":
    unittest.main()
