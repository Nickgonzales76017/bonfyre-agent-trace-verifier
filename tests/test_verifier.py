import copy
import json
import unittest
from pathlib import Path

from verifier import InputError, canonical_bytes, canonical_text, verify

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

    # --- identity continuity -------------------------------------------
    # A trace digest must not change when only the ENCODING of the content
    # changes. Two runs of the same agent on Windows and on Linux describe
    # the same execution; if they hash differently the digest is not an
    # identity. Both cases below were live bugs before v1.1.0, and are the
    # same class of bug found in bernstein#3695 during upstream review.

    def digest(self, trace):
        import hashlib
        return hashlib.sha256(canonical_bytes(trace)).hexdigest()

    def test_crlf_and_lf_produce_the_same_digest(self):
        crlf = {"snippet": "def f():\r\n    return 1\r\n"}
        lf = {"snippet": "def f():\n    return 1\n"}
        self.assertEqual(self.digest(crlf), self.digest(lf))

    def test_lone_cr_is_normalised_too(self):
        self.assertEqual(self.digest({"s": "a\rb"}), self.digest({"s": "a\nb"}))

    def test_unicode_nfd_and_nfc_produce_the_same_digest(self):
        import unicodedata
        nfc = unicodedata.normalize("NFC", "café")
        nfd = unicodedata.normalize("NFD", "café")
        self.assertNotEqual(nfc, nfd)                 # genuinely different strings
        self.assertEqual(self.digest({"m": nfc}), self.digest({"m": nfd}))

    def test_normal_form_is_normalised_in_keys_not_just_values(self):
        import unicodedata
        nfc = unicodedata.normalize("NFC", "café")
        nfd = unicodedata.normalize("NFD", "café")
        self.assertEqual(self.digest({nfc: 1}), self.digest({nfd: 1}))

    def test_normalisation_reaches_nested_structures(self):
        a = {"events": [{"log": "x\r\ny"}]}
        b = {"events": [{"log": "x\ny"}]}
        self.assertEqual(self.digest(a), self.digest(b))

    def test_int_and_float_forms_of_the_same_number_agree(self):
        self.assertEqual(self.digest({"n": 1}), self.digest({"n": 1.0}))

    def test_genuinely_different_content_still_differs(self):
        """Normalisation must not collapse real differences."""
        self.assertNotEqual(self.digest({"s": "a"}), self.digest({"s": "b"}))
        self.assertNotEqual(self.digest({"s": "ab"}), self.digest({"s": "a b"}))

    def test_booleans_are_not_coerced_to_numbers(self):
        self.assertNotEqual(self.digest({"v": True}), self.digest({"v": 1}))

    def test_canonical_text_is_idempotent(self):
        once = canonical_text("café\r\nx")
        self.assertEqual(once, canonical_text(once))

    def test_verified_trace_reports_canonicalization_version(self):
        result = verify(self.load("pass.json"))
        self.assertIn("canonicalization_version", result)

    def test_digest_is_stable_across_encoding_of_a_whole_trace(self):
        trace = self.load("pass.json")
        other = copy.deepcopy(trace)
        other["trace_id"] = trace["trace_id"]
        # re-encode every string in the trace as CRLF; behaviour is identical
        def crlf(v):
            if isinstance(v, str):
                return v.replace("\n", "\r\n")
            if isinstance(v, dict):
                return {k: crlf(x) for k, x in v.items()}
            if isinstance(v, list):
                return [crlf(x) for x in v]
            return v
        self.assertEqual(
            verify(trace)["trace_digest_sha256"],
            verify(crlf(other))["trace_digest_sha256"],
        )

    def test_missing_trace_id_is_input_error(self):
        trace = self.load("pass.json")
        del trace["trace_id"]
        with self.assertRaises(InputError):
            verify(trace)


if __name__ == "__main__":
    unittest.main()
