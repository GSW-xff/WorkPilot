.PHONY: dev db-up db-down migrate test lint typecheck check

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

lint:
	uv run ruff check workpilot tests apps alembic

typecheck:
	uv run mypy workpilot

check: lint typecheck test

