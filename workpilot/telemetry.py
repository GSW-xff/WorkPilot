from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

SAFE_ATTRIBUTE_PREFIXES = (
    "task.",
    "workflow.",
    "step.",
    "tool.",
    "gen_ai.",
    "workpilot.",
    "error.",
)


@dataclass(slots=True)
class SpanRecord:
    name: str
    attributes: dict[str, str | int | float | bool]
    duration_ms: float = 0
    status: str = "OK"


@dataclass(slots=True)
class MetricValue:
    count: float = 0
    sum: float = 0


class MetricsRegistry:
    def __init__(self) -> None:
        self._values: dict[tuple[str, tuple[tuple[str, str], ...]], MetricValue] = defaultdict(
            MetricValue
        )
        self._types: dict[str, str] = {}
        self._lock = threading.RLock()

    def counter(self, name: str, value: float = 1, **labels: str) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._types[name] = "counter"
            self._values[key].count += value

    def observe(self, name: str, value: float, **labels: str) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._types[name] = "summary"
            metric = self._values[key]
            metric.count += 1
            metric.sum += value

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name in sorted(self._types):
                metric_type = self._types[name]
                lines.append(f"# TYPE {name} {metric_type}")
                for (metric_name, labels), value in sorted(self._values.items()):
                    if metric_name != name:
                        continue
                    suffix = _labels(labels)
                    if metric_type == "summary":
                        lines.append(f"{name}_count{suffix} {value.count:g}")
                        lines.append(f"{name}_sum{suffix} {value.sum:g}")
                    else:
                        lines.append(f"{name}{suffix} {value.count:g}")
        return "\n".join(lines) + "\n"

    def snapshot(self) -> dict[str, dict[str, float]]:
        with self._lock:
            return {
                f"{name}{_labels(labels)}": {"count": value.count, "sum": value.sum}
                for (name, labels), value in self._values.items()
            }


class Telemetry:
    def __init__(self) -> None:
        self.tracer = trace.get_tracer("workpilot", "0.3.0")
        self.metrics = MetricsRegistry()
        self.finished_spans: list[SpanRecord] = []
        self._lock = threading.RLock()

    @contextmanager
    def span(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[SpanRecord]:
        safe = _safe_attributes(attributes or {})
        record = SpanRecord(name=name, attributes=safe)
        started = time.perf_counter()
        with self.tracer.start_as_current_span(name, attributes=safe) as otel_span:
            try:
                yield record
            except Exception as exc:
                record.status = "ERROR"
                otel_span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                otel_span.set_attribute("error.type", type(exc).__name__)
                raise
            finally:
                record.duration_ms = round((time.perf_counter() - started) * 1_000, 3)
                with self._lock:
                    self.finished_spans.append(record)

    def reset(self) -> None:
        with self._lock:
            self.finished_spans.clear()
        self.metrics = MetricsRegistry()

    def record_span(
        self,
        name: str,
        duration_ms: float,
        attributes: Mapping[str, Any] | None = None,
        *,
        error_type: str | None = None,
    ) -> None:
        safe = _safe_attributes(attributes or {})
        end_time = time.time_ns()
        start_time = end_time - int(duration_ms * 1_000_000)
        otel_span = self.tracer.start_span(name, attributes=safe, start_time=start_time)
        status = "ERROR" if error_type else "OK"
        if error_type:
            otel_span.set_status(Status(StatusCode.ERROR, error_type))
            otel_span.set_attribute("error.type", error_type)
        otel_span.end(end_time=end_time)
        with self._lock:
            self.finished_spans.append(
                SpanRecord(
                    name=name,
                    attributes=safe,
                    duration_ms=round(duration_ms, 3),
                    status=status,
                )
            )


TELEMETRY = Telemetry()


def configure_otlp(endpoint: str, service_name: str) -> None:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    TELEMETRY.tracer = trace.get_tracer("workpilot", "0.3.0")


def _safe_attributes(values: Mapping[str, Any]) -> dict[str, str | int | float | bool]:
    result: dict[str, str | int | float | bool] = {}
    for key, value in values.items():
        if not key.startswith(SAFE_ATTRIBUTE_PREFIXES):
            continue
        if isinstance(value, (str, int, float, bool)):
            result[key] = value
        elif value is not None:
            result[key] = json.dumps(value, sort_keys=True, ensure_ascii=False)[:500]
    return result


def _labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    content = ",".join(
        f'{key}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
        for key, value in labels
    )
    return "{" + content + "}"
