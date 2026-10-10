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

    def test_prometheus_rules_cover_measurable_slo_signals(self) -> None:
        prometheus = (ROOT / "deploy" / "observability" / "prometheus.yml").read_text()
        alerts = (ROOT / "deploy" / "observability" / "alerts.yml").read_text()
        compose = (ROOT / "deploy" / "docker-compose.yml").read_text()
        self.assertIn("alerts.yml", prometheus)
        self.assertIn("alertmanager:9093", prometheus)
        self.assertIn("alertmanager:", compose)
        for alert in (
            "WorkPilotApiAvailabilityBudgetBurn",
            "WorkPilotApiP95LatencyBudgetBurn",
            "WorkPilotTaskTerminalReliabilityBudgetBurn",
            "WorkPilotTraceCompletenessBudgetBurn",
            "WorkPilotToolErrorRateHigh",
            "WorkPilotPolicyDenialsDetected",
        ):
            with self.subTest(alert=alert):
                self.assertIn(alert, alerts)

    def test_backup_and_restore_drill_are_safe_and_verifiable(self) -> None:
        backup = (ROOT / "scripts" / "backup-postgres.sh").read_text()
        restore = (ROOT / "scripts" / "restore-drill-postgres.sh").read_text()
        self.assertIn("--format=custom", backup)
        self.assertIn("backup_sha256", backup)
        self.assertIn("WORKPILOT_BACKUP_DATABASE_USER", backup)
        self.assertIn('drill_database="workpilot_restore_drill"', restore)
        self.assertIn("restore_verification=passed", restore)
        self.assertIn("trap cleanup EXIT", restore)
        report = (ROOT / "docs" / "reports" / "backup-restore-drill.md").read_text()
        self.assertIn("最终结果：通过", report)
        self.assertIn("演练库清理后残留 | 0", report)


if __name__ == "__main__":
    unittest.main()
