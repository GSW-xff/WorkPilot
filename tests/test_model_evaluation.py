from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from workpilot.model_evaluation import (
    ModelComparisonRunner,
    ModelProfile,
    ModelProfiles,
    write_model_comparison,
)
from workpilot.model_gateway import DeterministicModelGateway
from workpilot.planner import DemoPlanner

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals" / "datasets" / "workpilot-v1.jsonl"


class ModelComparisonTest(unittest.IsolatedAsyncioTestCase):
    async def test_two_profiles_produce_cost_latency_trace_and_blind_review_artifacts(self) -> None:
        candidate = DemoPlanner().plan("prepare weekly report").model_dump(mode="json")
        profiles = ModelProfiles(
            profiles=[
                ModelProfile(
                    id="primary",
                    provider="contract",
                    model="primary-model",
                    base_url="https://models.test/v1",
                    api_key_env="PRIMARY_KEY",
                    input_cost_per_million=1,
                    output_cost_per_million=2,
                ),
                ModelProfile(
                    id="economy",
                    provider="contract",
                    model="economy-model",
                    base_url="https://models.test/v1",
                    api_key_env="ECONOMY_KEY",
                    input_cost_per_million=0.1,
                    output_cost_per_million=0.2,
                ),
            ]
        )
        report = await ModelComparisonRunner(
            gateway_factory=lambda _profile: DeterministicModelGateway(
                response_factory=lambda _messages: candidate
            ),
            execution_mode="contract_test",
        ).run(DATASET, profiles, repetitions=1)

        self.assertEqual(120, len(report.results))
        self.assertEqual(2, len(report.summaries))
        for summary in report.summaries:
            self.assertEqual(60, summary.runs)
            self.assertEqual(60, summary.passed)
            self.assertEqual(25, summary.model_invoked_runs)
            self.assertEqual(1, summary.native_plan_rate)
            self.assertEqual(0, summary.unauthorized_write)
            self.assertGreater(summary.input_tokens, 0)
            self.assertGreater(summary.total_cost_usd, 0)
            self.assertEqual(6, len(summary.categories))
            self.assertTrue(summary.quality_gate_passed)
            self.assertEqual([], summary.quality_gate_failures)

        with tempfile.TemporaryDirectory() as directory:
            paths = write_model_comparison(report, Path(directory))
            payload = json.loads(paths[0].read_text())
            self.assertEqual("contract_test", payload["execution_mode"])
            self.assertIn("deterministic_baseline", payload)
            review = paths[2].read_text()
            key = json.loads(paths[3].read_text())
            self.assertEqual(120, len(review.splitlines()))
            self.assertEqual(120, len(key))
            self.assertNotIn("primary-model", review)
            self.assertNotIn("economy-model", review)
            self.assertIn("prepare", review.lower())

    def test_profile_template_placeholders_are_rejected(self) -> None:
        template = ROOT / "evals" / "model-profiles.template.json"
        with self.assertRaisesRegex(ValueError, "placeholder"):
            ModelProfiles.model_validate_json(template.read_text())


if __name__ == "__main__":
    unittest.main()
