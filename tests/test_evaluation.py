from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from workpilot.evaluation import (
    DeterministicEvalRunner,
    enforce_safety_gate,
    load_dataset,
    write_baseline_comparison,
    write_report,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals" / "datasets" / "workpilot-v1.jsonl"


class EvaluationTest(unittest.TestCase):
    def test_dataset_has_sixty_versioned_cases_and_required_taxonomy(self) -> None:
        cases, digest = load_dataset(DATASET)
        self.assertGreaterEqual(len(cases), 60)
        self.assertEqual(64, len(digest))
        categories = {case.category for case in cases}
        self.assertEqual(
            {
                "normal",
                "ambiguous",
                "invalid_plan",
                "prompt_injection",
                "budget_or_cycle",
                "remote_failure",
            },
            categories,
        )
        self.assertTrue({"dev", "holdout"} <= {case.split for case in cases})
        self.assertTrue(all(case.scoring for case in cases))

    def test_runner_repeats_cases_and_generates_machine_and_human_reports(self) -> None:
        report = DeterministicEvalRunner().run(DATASET, repetitions=3)
        self.assertEqual(60, report.dataset_cases)
        self.assertEqual(180, len(report.results))
        self.assertIn("schema_valid", report.aggregate)
        self.assertIn("safety_pass", report.aggregate)
        self.assertEqual(1.0, report.aggregate["safety_pass"]["mean"])
        self.assertEqual(0.0, report.aggregate["unauthorized_write"]["mean"])
        self.assertEqual(1.0, report.aggregate["dag_valid"]["mean"])
        self.assertTrue(all(result.passed for result in report.results))
        self.assertEqual(
            {
                "ambiguous",
                "budget_or_cycle",
                "invalid_plan",
                "normal",
                "prompt_injection",
                "remote_failure",
            },
            set(report.categories),
        )
        self.assertTrue(
            all(category.pass_rate == 1 for category in report.categories.values())
        )
        self.assertTrue(
            all(
                category.aggregate["unauthorized_write"]["mean"] == 0
                for category in report.categories.values()
            )
        )
        enforce_safety_gate(report)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            json_path, markdown_path = write_report(report, output)
            comparison = write_baseline_comparison(report, output)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(60, payload["dataset_cases"])
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("Results by category", markdown)
            self.assertIn("Failure taxonomy", markdown)
            self.assertIn("comparison floor", comparison.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
