from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any, Protocol, TypeVar
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class Message(BaseModel):
    role: str
    content: str
    source: str = "workpilot"
    trust: str = "trusted"


class ModelPolicy(BaseModel):
    provider: str
    model: str
    prompt_version: str = "planner-v1"
    schema_version: str = "task-plan-v1"
    timeout_seconds: float = Field(default=30, gt=0, le=120)
    max_retries: int = Field(default=1, ge=0, le=3)
    input_cost_per_million: float = Field(default=0, ge=0)
    output_cost_per_million: float = Field(default=0, ge=0)


class RunBudget(BaseModel):
    max_input_tokens: int = Field(default=8_000, gt=0)
    max_output_tokens: int = Field(default=2_000, gt=0)
    max_cost_usd: float = Field(default=0.25, ge=0)
    max_latency_ms: int = Field(default=30_000, gt=0)


class ModelCallRecord(BaseModel):
    provider: str
    model: str
    request_id: str
    prompt_version: str
    schema_version: str
    input_tokens: int = 0
    output_tokens: int = 0
    first_token_ms: float | None = None
    total_latency_ms: float = 0
    retry_count: int = 0
    error_type: str | None = None
    fallback_reason: str | None = None
    cache_hit: bool = False
    estimated_cost_usd: float = 0
    trace_id: str
    tenant_id: str
    task_id: str


class ModelResponse(BaseModel):
    output: dict[str, Any]
    record: ModelCallRecord


class ModelGatewayError(RuntimeError):
    def __init__(self, message: str, *, error_type: str = "provider_error") -> None:
        super().__init__(message)
        self.error_type = error_type


class BudgetExceededError(ModelGatewayError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_type="budget_exceeded")


class ModelGateway(Protocol):
    async def generate_structured(
        self,
        *,
        messages: list[Message],
        output_schema: type[SchemaT],
        model_policy: ModelPolicy,
        budget: RunBudget,
        metadata: dict[str, str],
    ) -> ModelResponse: ...


def estimate_tokens(text: str) -> int:
    """Conservative provider-independent estimate suitable for enforcing a hard preflight cap."""
    if not text:
        return 0
    ascii_count = sum(character.isascii() for character in text)
    non_ascii_count = len(text) - ascii_count
    return max(1, (ascii_count + 3) // 4 + non_ascii_count)


def estimate_message_tokens(messages: list[Message]) -> int:
    return sum(estimate_tokens(item.content) + 4 for item in messages)


class DeterministicModelGateway:
    """Offline structured provider used by unit tests, CI and reproducible evaluations."""

    def __init__(
        self,
        responses: list[dict[str, Any]] | None = None,
        response_factory: Callable[[list[Message]], dict[str, Any]] | None = None,
    ) -> None:
        self._responses = list(responses or [])
        self._response_factory = response_factory
        self.calls: list[list[Message]] = []

    async def generate_structured(
        self,
        *,
        messages: list[Message],
        output_schema: type[SchemaT],
        model_policy: ModelPolicy,
        budget: RunBudget,
        metadata: dict[str, str],
    ) -> ModelResponse:
        del output_schema
        started = time.perf_counter()
        input_tokens = estimate_message_tokens(messages)
        if input_tokens > budget.max_input_tokens:
            raise BudgetExceededError("model input exceeds token budget")
        self.calls.append([item.model_copy(deep=True) for item in messages])
        if self._responses:
            output = self._responses.pop(0)
        elif self._response_factory:
            output = self._response_factory(messages)
        else:
            raise ModelGatewayError("deterministic gateway has no response", error_type="empty")
        output_tokens = estimate_tokens(json.dumps(output, ensure_ascii=False))
        if output_tokens > budget.max_output_tokens:
            raise BudgetExceededError("model output exceeds token budget")
        cost = _estimated_cost(input_tokens, output_tokens, model_policy)
        if cost > budget.max_cost_usd:
            raise BudgetExceededError("model response exceeds cost budget")
        return ModelResponse(
            output=output,
            record=_record(
                model_policy,
                metadata,
                request_id=f"fake-{uuid4().hex[:12]}",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=(time.perf_counter() - started) * 1_000,
                cost=cost,
            ),
        )


class OpenAICompatibleModelGateway:
    """Cloud provider adapter using the OpenAI-compatible chat-completions contract."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = client

    async def generate_structured(
        self,
        *,
        messages: list[Message],
        output_schema: type[SchemaT],
        model_policy: ModelPolicy,
        budget: RunBudget,
        metadata: dict[str, str],
    ) -> ModelResponse:
        input_tokens = estimate_message_tokens(messages)
        if input_tokens > budget.max_input_tokens:
            raise BudgetExceededError("model input exceeds token budget")
        payload = {
            "model": model_policy.model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
            "max_tokens": budget.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output_schema.__name__,
                    "strict": True,
                    "schema": output_schema.model_json_schema(),
                },
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Request-ID": metadata.get("request_id", str(uuid4())),
        }
        client = self._client or httpx.AsyncClient()
        owns_client = self._client is None
        started = time.perf_counter()
        retries = 0
        try:
            while True:
                try:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=min(
                            model_policy.timeout_seconds,
                            budget.max_latency_ms / 1_000,
                        ),
                    )
                    if response.status_code == 429 or response.status_code >= 500:
                        if retries < model_policy.max_retries:
                            retry_after = min(float(response.headers.get("Retry-After", 0.1)), 2)
                            retries += 1
                            await asyncio.sleep(retry_after)
                            continue
                    response.raise_for_status()
                    body = response.json()
                    content = body["choices"][0]["message"]["content"]
                    output = json.loads(content) if isinstance(content, str) else content
                    usage = body.get("usage", {})
                    actual_input = int(usage.get("prompt_tokens", input_tokens))
                    output_tokens = int(
                        usage.get(
                            "completion_tokens",
                            estimate_tokens(json.dumps(output, ensure_ascii=False)),
                        )
                    )
                    cost = _estimated_cost(actual_input, output_tokens, model_policy)
                    if cost > budget.max_cost_usd:
                        raise BudgetExceededError("model response exceeds cost budget")
                    return ModelResponse(
                        output=output,
                        record=_record(
                            model_policy,
                            metadata,
                            request_id=str(body.get("id") or headers["X-Request-ID"]),
                            input_tokens=actual_input,
                            output_tokens=output_tokens,
                            latency_ms=(time.perf_counter() - started) * 1_000,
                            cost=cost,
                            retry_count=retries,
                        ),
                    )
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if retries < model_policy.max_retries:
                        retries += 1
                        await asyncio.sleep(min(0.1 * 2**retries, 2))
                        continue
                    error_type = "timeout" if isinstance(exc, httpx.TimeoutException) else "network"
                    raise ModelGatewayError(str(exc), error_type=error_type) from exc
                except (KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise ModelGatewayError(
                        "provider returned an invalid structured response",
                        error_type="invalid_response",
                    ) from exc
                except httpx.HTTPStatusError as exc:
                    raise ModelGatewayError(
                        f"provider HTTP {exc.response.status_code}",
                        error_type="rate_limit"
                        if exc.response.status_code == 429
                        else "provider_error",
                    ) from exc
        finally:
            if owns_client:
                await client.aclose()


def _estimated_cost(input_tokens: int, output_tokens: int, model_policy: ModelPolicy) -> float:
    return round(
        input_tokens * model_policy.input_cost_per_million / 1_000_000
        + output_tokens * model_policy.output_cost_per_million / 1_000_000,
        8,
    )


def _record(
    policy: ModelPolicy,
    metadata: dict[str, str],
    *,
    request_id: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    cost: float,
    retry_count: int = 0,
) -> ModelCallRecord:
    return ModelCallRecord(
        provider=policy.provider,
        model=policy.model,
        request_id=request_id,
        prompt_version=policy.prompt_version,
        schema_version=policy.schema_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_latency_ms=round(latency_ms, 3),
        retry_count=retry_count,
        estimated_cost_usd=cost,
        trace_id=metadata.get("trace_id", uuid4().hex),
        tenant_id=metadata.get("tenant_id", "unknown"),
        task_id=metadata.get("task_id", "unknown"),
    )
