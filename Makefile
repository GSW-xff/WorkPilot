.PHONY: dev db-up db-down migrate test test-temporal lint typecheck check

dev:
	uv run workpilot

db-up:
	docker compose -f deploy/docker-compose.yml up -d postgres

db-down:
	docker compose -f deploy/docker-compose.yml down

migrate:
	uv run alembic upgrade head

test:
	uv run pytest

test-temporal:
	WORKPILOT_RUN_TEMPORAL_INTEGRATION=1 uv run pytest tests/test_temporal_integration.py

lint:
	uv run ruff check workpilot tests apps alembic

typecheck:
	uv run mypy workpilot

check: lint typecheck test
