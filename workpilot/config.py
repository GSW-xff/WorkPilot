from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str | None = None
    auto_create_schema: bool = False
    max_steps: int = 20
    allowed_recipient_domains: frozenset[str] = frozenset({"example.com"})
    temporal_target: str | None = None
    temporal_task_queue: str = "workpilot-tasks"
    planner_mode: str = "demo"
    model_base_url: str = "https://api.openai.com/v1"
    model_api_key: str | None = None
    model_name: str = "gpt-4.1-mini"
    model_input_budget: int = 8_000
    model_output_budget: int = 2_000
    model_cost_budget_usd: float = 0.25
    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_oauth_state_secret: str | None = None
    github_redirect_uri: str = "http://127.0.0.1:8000/v1/connectors/github/callback"
    github_webhook_secret: str | None = None
    otlp_endpoint: str | None = None
    service_name: str = "workpilot-api"
    auth_mode: str = "headers"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    knowledge_object_dir: str = "/tmp/workpilot-objects"
    knowledge_max_file_bytes: int = 10 * 1024 * 1024

    @classmethod
    def from_env(cls) -> Settings:
        database_url = os.getenv("WORKPILOT_DATABASE_URL") or None
        domains = frozenset(
            item.strip().lower()
            for item in os.getenv("WORKPILOT_ALLOWED_RECIPIENT_DOMAINS", "example.com").split(",")
            if item.strip()
        )
        return cls(
            host=os.getenv("WORKPILOT_HOST", "127.0.0.1"),
            port=int(os.getenv("WORKPILOT_PORT", "8000")),
            database_url=database_url,
            auto_create_schema=_as_bool(os.getenv("WORKPILOT_AUTO_CREATE_SCHEMA"), default=False),
            max_steps=int(os.getenv("WORKPILOT_MAX_STEPS", "20")),
            allowed_recipient_domains=domains or frozenset({"example.com"}),
            temporal_target=os.getenv("WORKPILOT_TEMPORAL_TARGET") or None,
            temporal_task_queue=os.getenv("WORKPILOT_TEMPORAL_TASK_QUEUE", "workpilot-tasks"),
            planner_mode=os.getenv("WORKPILOT_PLANNER_MODE", "demo").strip().lower(),
            model_base_url=os.getenv("WORKPILOT_MODEL_BASE_URL", "https://api.openai.com/v1"),
            model_api_key=os.getenv("WORKPILOT_MODEL_API_KEY") or None,
            model_name=os.getenv("WORKPILOT_MODEL_NAME", "gpt-4.1-mini"),
            model_input_budget=int(os.getenv("WORKPILOT_MODEL_INPUT_BUDGET", "8000")),
            model_output_budget=int(os.getenv("WORKPILOT_MODEL_OUTPUT_BUDGET", "2000")),
            model_cost_budget_usd=float(os.getenv("WORKPILOT_MODEL_COST_BUDGET_USD", "0.25")),
            github_client_id=os.getenv("WORKPILOT_GITHUB_CLIENT_ID") or None,
            github_client_secret=os.getenv("WORKPILOT_GITHUB_CLIENT_SECRET") or None,
            github_oauth_state_secret=os.getenv("WORKPILOT_GITHUB_STATE_SECRET") or None,
            github_redirect_uri=os.getenv(
                "WORKPILOT_GITHUB_REDIRECT_URI",
                "http://127.0.0.1:8000/v1/connectors/github/callback",
            ),
            github_webhook_secret=os.getenv("WORKPILOT_GITHUB_WEBHOOK_SECRET") or None,
            otlp_endpoint=os.getenv("WORKPILOT_OTLP_ENDPOINT") or None,
            service_name=os.getenv("WORKPILOT_SERVICE_NAME", "workpilot-api"),
            auth_mode=os.getenv("WORKPILOT_AUTH_MODE", "headers").strip().lower(),
            oidc_issuer=os.getenv("WORKPILOT_OIDC_ISSUER") or None,
            oidc_audience=os.getenv("WORKPILOT_OIDC_AUDIENCE") or None,
            oidc_jwks_url=os.getenv("WORKPILOT_OIDC_JWKS_URL") or None,
            knowledge_object_dir=os.getenv(
                "WORKPILOT_KNOWLEDGE_OBJECT_DIR", "/tmp/workpilot-objects"
            ),
            knowledge_max_file_bytes=int(
                os.getenv("WORKPILOT_KNOWLEDGE_MAX_FILE_BYTES", str(10 * 1024 * 1024))
            ),
        )
