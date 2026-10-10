import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class DeploymentAssetsTest(unittest.TestCase):
    def test_helm_chart_has_runtime_reliability_and_security_controls(self) -> None:
        chart = ROOT / "deploy" / "helm" / "workpilot"
        content = "\n".join(path.read_text() for path in chart.rglob("*.*") if path.is_file())
        required = [
            "kind: Deployment",
            "workpilot-api",
            "workpilot-worker",
            "readinessProbe",
            "livenessProbe",
            "startupProbe",
            "readOnlyRootFilesystem: true",
            "runAsNonRoot: true",
            'capabilities: {drop: ["ALL"]}',
            "kind: PodDisruptionBudget",
            "kind: NetworkPolicy",
            "kind: ScaledObject",
            "temporal_task_queue_backlog",
        ]
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, content)

    def test_supply_chain_workflow_has_expected_gates(self) -> None:
        content = (ROOT / ".github" / "workflows" / "supply-chain.yml").read_text()
        for gate in (
            "github/codeql-action",
            "dependency-review-action",
            "trivy-action",
            "anchore/sbom-action",
            "attest-sbom",
            "helm lint",
        ):
            with self.subTest(gate=gate):
                self.assertIn(gate, content)

    def test_runtime_image_contains_console_reports_and_benchmark_package(self) -> None:
        content = (ROOT / "Dockerfile").read_text()
        self.assertIn("COPY apps ./apps", content)
        self.assertIn("COPY evals ./evals", content)
        self.assertIn("COPY benchmarks ./benchmarks", content)


if __name__ == "__main__":
    unittest.main()
