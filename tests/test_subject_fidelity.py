import json
import unittest
from pathlib import Path

from verifier import verify

ROOT = Path(__file__).resolve().parents[1]


class SubjectFidelityTests(unittest.TestCase):
    def load(self):
        return json.loads((ROOT / "examples" / "pass.json").read_text())

    def read_event(self, event_id, **extra):
        event = {
            "event_id": event_id,
            "actor": "support-agent",
            "action": "observe_runtime",
            "resource": "runtime:subject",
            "effect": "read",
            "authority": "ticket:read",
            "status": "succeeded",
            "cost_usd": 0.0,
        }
        event.update(extra)
        return event

    def test_context_compaction_is_first_class_and_measurable(self):
        trace = self.load()
        trace["task"]["require_context_events"] = True
        trace["task"]["max_steps"] = 4
        trace["events"].append(
            self.read_event(
                "evt-context",
                event_type="context_compaction",
                context={
                    "before_tokens": 12000,
                    "after_tokens": 6200,
                    "strategy": "summary+anchors",
                },
            )
        )
        result = verify(trace)
        self.assertTrue(result["dimensions"]["context_management"]["passed"])
        self.assertEqual(result["metrics"]["context_event_count"], 1)

    def test_required_context_events_cannot_be_silently_omitted(self):
        trace = self.load()
        trace["task"]["require_context_events"] = True
        result = verify(trace)
        self.assertFalse(result["dimensions"]["context_management"]["passed"])

    def test_subject_provider_and_host_evidence_are_not_mixed(self):
        trace = self.load()
        trace["task"].update(
            {
                "require_provider_fidelity": True,
                "subject_provider": "anthropic",
                "max_steps": 5,
            }
        )
        trace["events"].extend(
            [
                self.read_event(
                    "evt-subject-turn",
                    event_type="model_turn",
                    provider="anthropic",
                    evidence_origin="subject",
                ),
                self.read_event(
                    "evt-host-eval",
                    event_type="model_turn",
                    provider="openai",
                    evidence_origin="host",
                ),
            ]
        )
        result = verify(trace)
        self.assertTrue(result["dimensions"]["provider_fidelity"]["passed"])
        self.assertEqual(result["metrics"]["subject_model_turn_count"], 1)
        self.assertEqual(result["metrics"]["non_subject_model_turn_count"], 1)

    def test_subject_turn_on_substitute_provider_fails_fidelity(self):
        trace = self.load()
        trace["task"].update(
            {
                "require_provider_fidelity": True,
                "subject_provider": "anthropic",
                "max_steps": 4,
            }
        )
        trace["events"].append(
            self.read_event(
                "evt-substitute",
                event_type="model_turn",
                provider="openai",
                evidence_origin="subject",
            )
        )
        result = verify(trace)
        self.assertFalse(result["dimensions"]["provider_fidelity"]["passed"])

    def test_adapter_capability_differences_are_explicit(self):
        trace = self.load()
        trace["task"]["required_capabilities"] = ["tool_calls", "context_events"]
        trace["adapter_capabilities"] = {
            "available": ["tool_calls", "context_events"],
            "unavailable": ["native_compaction_hook"],
        }
        result = verify(trace)
        self.assertTrue(result["dimensions"]["adapter_capabilities"]["passed"])
        self.assertEqual(
            result["metrics"]["adapter_unavailable_capabilities"],
            ["native_compaction_hook"],
        )

    def test_required_adapter_capability_cannot_be_widened_silently(self):
        trace = self.load()
        trace["task"]["required_capabilities"] = ["tool_calls", "context_events"]
        trace["adapter_capabilities"] = {
            "available": ["tool_calls"],
            "unavailable": ["context_events"],
        }
        result = verify(trace)
        self.assertFalse(result["dimensions"]["adapter_capabilities"]["passed"])


if __name__ == "__main__":
    unittest.main()
