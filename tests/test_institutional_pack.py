import unittest

from conformance.institutional_pack.validate import validate_all


class InstitutionalPackTests(unittest.TestCase):
    def test_all_pinned_artifacts_validate_offline(self):
        result = validate_all()
        self.assertEqual(result["opentelemetry"]["spans"], 3)
        self.assertEqual(result["openssf_osps"]["fail"], 1)
        self.assertFalse(result["slsa"]["signed"])
        self.assertEqual(result["habitat"]["rooms"], 3)
        self.assertEqual(result["bonfyre_contracts"]["public_commands"], 91)
        self.assertEqual(result["frappe"]["app_powers"], 9)


if __name__ == "__main__":
    unittest.main()
