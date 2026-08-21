import copy
import json
import unicodedata
import unittest
from pathlib import Path

from verifier import InputError, verify

ROOT = Path(__file__).resolve().parents[1]


class ProviderIdentityContractTests(unittest.TestCase):
    def load(self):
        return json.loads((ROOT / "examples" / "subject-fidelity.json").read_text())

    def test_nfc_nfd_provider_spellings_are_the_same_receipt(self):
        # Use a provider label with a composed character so the two Python
        # strings are genuinely distinct while the canonical trace identity is
        # intentionally the same.
        nfc = unicodedata.normalize("NFC", "café-provider")
        nfd = unicodedata.normalize("NFD", "café-provider")
        self.assertNotEqual(nfc, nfd)

        left = self.load()
        right = copy.deepcopy(left)
        left["task"]["subject_provider"] = nfc
        left["events"][1]["provider"] = nfc
        right["task"]["subject_provider"] = nfd
        right["events"][1]["provider"] = nfd

        left_receipt = verify(left)
        right_receipt = verify(right)

        self.assertTrue(left_receipt["dimensions"]["provider_fidelity"]["passed"])
        self.assertTrue(right_receipt["dimensions"]["provider_fidelity"]["passed"])
        self.assertEqual(left_receipt, right_receipt)
        self.assertEqual(left_receipt["metrics"]["subject_provider"], nfc)

    def test_real_provider_difference_still_fails(self):
        trace = self.load()
        trace["events"][1]["provider"] = "different-provider"

        result = verify(trace)

        self.assertFalse(result["dimensions"]["provider_fidelity"]["passed"])

    def test_explicit_empty_required_capabilities_remains_optional(self):
        trace = self.load()
        trace["task"]["required_capabilities"] = []
        del trace["adapter_capabilities"]

        result = verify(trace)

        self.assertNotIn("adapter_capabilities", result["dimensions"])

    def test_absent_required_capabilities_remains_optional(self):
        trace = self.load()
        del trace["task"]["required_capabilities"]
        del trace["adapter_capabilities"]

        result = verify(trace)

        self.assertNotIn("adapter_capabilities", result["dimensions"])

    def test_explicit_null_adapter_capabilities_is_malformed(self):
        trace = self.load()
        trace["task"]["required_capabilities"] = []
        trace["adapter_capabilities"] = None

        with self.assertRaises(InputError):
            verify(trace)


for _name, _value in (
    ("null", None),
    ("false", False),
    ("zero", 0),
    ("empty-string", ""),
):
    def _make_test(value):
        def test(self):
            trace = self.load()
            trace["task"]["required_capabilities"] = value
            del trace["adapter_capabilities"]
            with self.assertRaises(InputError):
                verify(trace)
        return test

    setattr(
        ProviderIdentityContractTests,
        "test_falsey_non_array_required_capabilities_" + _name.replace("-", "_"),
        _make_test(_value),
    )


if __name__ == "__main__":
    unittest.main()
