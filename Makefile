.PHONY: benchmark dev db-up db-down helm-lint migrate test test-browser test-postgres test-temporal lint typecheck check

benchmark:
	uv run workpilot-benchmark

dev:
	uv run workpilot

db-up:
	docker compose -f deploy/docker-compose.yml up -d postgres

db-down:
	docker compose -f deploy/docker-compose.yml down

migrate:
	uv run alembic upgrade head

helm-lint:
	helm lint deploy/helm/workpilot

test:
	uv run pytest

test-temporal:
	WORKPILOT_RUN_TEMPORAL_INTEGRATION=1 uv run pytest tests/test_temporal_integration.py

test-postgres:
	WORKPILOT_RUN_POSTGRES_INTEGRATION=1 uv run pytest tests/test_postgres_rls_integration.py

test-browser:
	WORKPILOT_RUN_BROWSER_INTEGRATION=1 uv run pytest tests/test_browser_adapter.py

lint:
	uv run ruff check workpilot tests apps alembic

typecheck:
	uv run mypy workpilot

check: lint typecheck test
