import unittest
from pathlib import Path

from workpilot.retrieval_evaluation import evaluate, render_markdown


class RetrievalEvaluationTest(unittest.TestCase):
    def test_fixed_dataset_reports_all_modes_and_citation_quality(self) -> None:
        report = evaluate(Path("evals/retrieval_cases.jsonl"))
        self.assertEqual(10, report["case_count"])
        self.assertEqual({"lexical", "vector", "hybrid_rrf"}, set(report["modes"]))
        self.assertGreaterEqual(report["modes"]["hybrid_rrf"]["recall_at_5"], 0.9)
        self.assertGreaterEqual(report["modes"]["lexical"]["citation_precision_at_1"], 0.9)
        self.assertIn("Citation precision@1", render_markdown(report))


if __name__ == "__main__":
    unittest.main()
