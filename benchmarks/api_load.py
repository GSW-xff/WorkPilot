from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from workpilot.api import create_app


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


async def run(iterations: int = 300, concurrency: int = 20) -> dict[str, Any]:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    semaphore = asyncio.Semaphore(concurrency)
    timings: dict[str, list[float]] = {"create_task": [], "list_tasks": []}
    statuses: Counter[int] = Counter()

    async with httpx.AsyncClient(transport=transport, base_url="http://benchmark") as client:

        async def operation(index: int) -> None:
            async with semaphore:
                operation_name = "create_task" if index % 3 == 0 else "list_tasks"
                started = time.perf_counter()
                if operation_name == "create_task":
                    response = await client.post(
                        "/v1/tasks",
                        headers={
                            "X-Tenant-ID": f"tenant-{index % 10}",
                            "X-User-ID": "load-test",
                            "Idempotency-Key": f"load-{index}",
                        },
                        json={"goal": f"prepare deterministic report {index}"},
                    )
                else:
                    response = await client.get(
                        "/v1/tasks?limit=20",
                        headers={"X-Tenant-ID": f"tenant-{index % 10}"},
                    )
                timings[operation_name].append((time.perf_counter() - started) * 1_000)
                statuses[response.status_code] += 1

        started = time.perf_counter()
        await asyncio.gather(*(operation(index) for index in range(iterations)))
        elapsed = time.perf_counter() - started
    app.state.service.repository.close()

    successful = sum(count for status, count in statuses.items() if status < 400)
    return {
        "profile": {
            "transport": "in-process ASGI",
            "storage": "memory",
            "planner": "deterministic demo",
            "iterations": iterations,
            "concurrency": concurrency,
            "paid_model_calls": 0,
        },
        "throughput_rps": round(iterations / elapsed, 2),
        "elapsed_seconds": round(elapsed, 4),
        "error_rate": round((iterations - successful) / iterations, 6),
        "statuses": dict(statuses),
        "operations": {
            name: {
                "count": len(values),
                "mean_ms": round(statistics.mean(values), 3),
                "p50_ms": round(percentile(values, 0.50), 3),
                "p95_ms": round(percentile(values, 0.95), 3),
                "p99_ms": round(percentile(values, 0.99), 3),
            }
            for name, values in timings.items()
        },
        "capacity_note": (
            "This isolates API/framework overhead. PostgreSQL pool, Temporal queue lag, "
            "worker saturation and external SaaS latency require the Compose/staging profile."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    profile = report["profile"]
    lines = [
        "# API load baseline",
        "",
        f"Profile: {profile['transport']}, {profile['storage']}, {profile['planner']}",
        f"Load: {profile['iterations']} operations at concurrency {profile['concurrency']}",
        "",
        f"- Throughput: **{report['throughput_rps']:.2f} req/s**",
        f"- Error rate: **{report['error_rate']:.2%}**",
        f"- Elapsed: **{report['elapsed_seconds']:.4f}s**",
        "",
        "| Operation | Count | Mean ms | P50 ms | P95 ms | P99 ms |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, metric in report["operations"].items():
        lines.append(
            f"| {name} | {metric['count']} | {metric['mean_ms']:.3f} | "
            f"{metric['p50_ms']:.3f} | {metric['p95_ms']:.3f} | {metric['p99_ms']:.3f} |"
        )
    lines.extend(["", f"> {report['capacity_note']}", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/reports/api-baseline-v1"))
    args = parser.parse_args()
    report = asyncio.run(run(args.iterations, args.concurrency))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.output / "report.md").write_text(render_markdown(report))


if __name__ == "__main__":
    main()
