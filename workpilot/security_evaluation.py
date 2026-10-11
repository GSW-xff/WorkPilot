from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from workpilot.connectors.base import ConnectorRejected
from workpilot.context import detect_prompt_injection
from workpilot.mcp import validate_mcp_description
from workpilot.resources import bundled_path
from workpilot.security import redact


def evaluate_case(case: dict[str, Any]) -> str:
    payload = case["input"]
    if case["check"] == "injection":
        return "flagged" if detect_prompt_injection(payload["content"]) else "clean"
    if case["check"] == "redaction":
        serialized = json.dumps(redact(payload["value"]))
        return "redacted" if payload["secret"] not in serialized else "leaked"
    if case["check"] == "mcp_description":
        try:
            validate_mcp_description(payload["description"])
        except ConnectorRejected:
            return "rejected"
        return "accepted"
    if case["check"] == "tool_risk":
        return "accepted" if payload["risk"] == "R0" else "rejected"
    if case["check"] == "scope":
        return (
            "accepted"
            if set(payload["requested"]).issubset(set(payload["granted"]))
            else "rejected"
        )
    if case["check"] == "tenant":
        return "accepted" if payload["resource_tenant"] == payload["request_tenant"] else "rejected"
    raise ValueError(f"unknown security check: {case['check']}")


def run(dataset_path: Path) -> dict[str, Any]:
    cases = [json.loads(line) for line in dataset_path.read_text().splitlines() if line.strip()]
    results = []
    category_total: Counter[str] = Counter()
    category_passed: Counter[str] = Counter()
    for case in cases:
        observed = evaluate_case(case)
        passed = observed == case["expected"]
        category_total[case["category"]] += 1
        category_passed[case["category"]] += int(passed)
        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "expected": case["expected"],
                "observed": observed,
                "passed": passed,
            }
        )
    return {
        "dataset": dataset_path.name,
        "case_count": len(cases),
        "passed": sum(item["passed"] for item in results),
        "pass_rate": round(sum(item["passed"] for item in results) / len(cases), 4),
        "categories": {
            category: {
                "passed": category_passed[category],
                "total": total,
                "pass_rate": round(category_passed[category] / total, 4),
            }
            for category, total in sorted(category_total.items())
        },
        "results": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Agentic security regression",
        "",
        f"Result: **{report['passed']}/{report['case_count']}** ({report['pass_rate']:.1%})",
        "",
        "| Category | Passed | Total | Pass rate |",
        "|---|---:|---:|---:|",
    ]
    for category, result in report["categories"].items():
        lines.append(
            f"| {category} | {result['passed']} | {result['total']} | {result['pass_rate']:.1%} |"
        )
    lines.extend(
        [
            "",
            "This deterministic policy-gate suite does not replace penetration testing.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=bundled_path("evals", "security_cases.jsonl"),
    )
    parser.add_argument("--output", type=Path, default=Path("evals/reports/security-v1"))
    args = parser.parse_args()
    report = run(args.dataset)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    (args.output / "report.md").write_text(render_markdown(report))


if __name__ == "__main__":
    main()
