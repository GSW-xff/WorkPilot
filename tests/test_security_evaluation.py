import unittest
from pathlib import Path

from workpilot.security_evaluation import render_markdown, run


class SecurityEvaluationTest(unittest.TestCase):
    def test_versioned_security_suite_passes_all_policy_gates(self) -> None:
        report = run(Path("evals/security_cases.jsonl"))
        self.assertEqual(20, report["case_count"])
        self.assertEqual(20, report["passed"])
        self.assertEqual(1.0, report["pass_rate"])
        self.assertEqual(
            {
                "excessive_agency",
                "mcp_poisoning",
                "prompt_injection",
                "scope_escalation",
                "secret_leakage",
                "tenant_isolation",
            },
            set(report["categories"]),
        )
        self.assertIn("does not replace penetration testing", render_markdown(report))


if __name__ == "__main__":
    unittest.main()
