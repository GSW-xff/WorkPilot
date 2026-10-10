from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from typing import Any

from workpilot.knowledge import KnowledgeService, LocalObjectStore


def evaluate(dataset_path: Path) -> dict[str, Any]:
    cases = [json.loads(line) for line in dataset_path.read_text().splitlines() if line.strip()]
    modes: dict[str, dict[str, float]] = {}
    with tempfile.TemporaryDirectory() as directory:
        service = KnowledgeService(LocalObjectStore(Path(directory)))
        document_ids: dict[tuple[str, str], str] = {}
        for case in cases:
            for filename, content in case["corpus"].items():
                document = service.ingest(
                    tenant_id=case["id"],
                    owner_id="evaluator",
                    filename=filename,
                    media_type="text/markdown",
                    content=content.encode(),
                )
                document_ids[(case["id"], filename)] = document.id

        for mode in ("lexical", "vector", "hybrid_rrf"):
            reciprocal_ranks: list[float] = []
            recalls: list[float] = []
            ndcgs: list[float] = []
            citation_hits: list[float] = []
            for case in cases:
                expected = document_ids[(case["id"], case["relevant"])]
                results = service.search(
                    tenant_id=case["id"],
                    user_id="evaluator",
                    query=case["query"],
                    top_k=5,
                    mode=mode,
                )
                ranked = [item.document_id for item in results]
                rank = ranked.index(expected) + 1 if expected in ranked else None
                reciprocal_ranks.append(1 / rank if rank else 0)
                recalls.append(1.0 if rank else 0.0)
                ndcgs.append(1 / math.log2(rank + 1) if rank else 0.0)
                citation_hits.append(1.0 if results and results[0].document_id == expected else 0.0)
            modes[mode] = {
                "recall_at_5": round(sum(recalls) / len(cases), 4),
                "mrr": round(sum(reciprocal_ranks) / len(cases), 4),
                "ndcg_at_5": round(sum(ndcgs) / len(cases), 4),
                "citation_precision_at_1": round(sum(citation_hits) / len(cases), 4),
            }
    return {"dataset": dataset_path.name, "case_count": len(cases), "modes": modes}


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Retrieval evaluation",
        "",
        f"Dataset: `{report['dataset']}` ({report['case_count']} cases)",
        "",
        "| Mode | Recall@5 | MRR | nDCG@5 | Citation precision@1 |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode, metrics in report["modes"].items():
        lines.append(
            f"| {mode} | {metrics['recall_at_5']:.4f} | {metrics['mrr']:.4f} | "
            f"{metrics['ndcg_at_5']:.4f} | {metrics['citation_precision_at_1']:.4f} |"
        )
    lines.extend(
        [
            "",
            "The deterministic hash embedding is an offline baseline, not a hosted-model claim.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("evals/retrieval_cases.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("evals/reports/retrieval-v1"))
    args = parser.parse_args()
    report = evaluate(args.dataset)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    (args.output / "report.md").write_text(render_markdown(report))


if __name__ == "__main__":
    main()
