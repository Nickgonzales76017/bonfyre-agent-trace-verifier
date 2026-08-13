import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "environments" / "helpdesk_sla"))

from environment import HelpdeskSLAEnvironment, InvalidAction
from verifier import verify


ACTIONS = [
    {"action": "read_ticket"},
    {"action": "assign_tier2", "evidence": "receipt:ticket-version-2"},
    {
        "action": "send_resolution",
        "reviewer": "human:operator-3",
        "evidence": "receipt:message-882",
    },
    {"action": "close_ticket", "evidence": "receipt:ticket-version-3"},
]


class HelpdeskEnvironmentTests(unittest.TestCase):
    def test_reset_is_content_addressed_and_deterministic(self):
        environment = HelpdeskSLAEnvironment()
        first = environment.observe()
        environment.step("read_ticket")
        second = environment.reset()
        self.assertEqual(first, second)

    def test_branch_does_not_mutate_actual_state(self):
        actual = HelpdeskSLAEnvironment()
        candidate = actual.branch()
        candidate.step("assign_tier2", evidence="receipt:ticket-version-2")
        self.assertEqual("tier1", actual.state["ticket"]["assigned_team"])
        self.assertEqual("tier2", candidate.state["ticket"]["assigned_team"])

    def test_replay_is_deterministic_and_verifies(self):
        first = HelpdeskSLAEnvironment.replay(ACTIONS)
        second = HelpdeskSLAEnvironment.replay(ACTIONS)
        self.assertEqual(first.observe()["state_id"], second.observe()["state_id"])
        receipt = verify(first.trace())
        self.assertTrue(receipt["passed"])
        self.assertEqual(4, receipt["metrics"]["event_count"])

    def test_external_send_requires_review(self):
        environment = HelpdeskSLAEnvironment()
        environment.step("assign_tier2", evidence="receipt:ticket-version-2")
        with self.assertRaises(InvalidAction):
            environment.step("send_resolution", evidence="receipt:message-882")


if __name__ == "__main__":
    unittest.main()
