.PHONY: backup benchmark build check db-down db-up dev eval-models eval-safety github-sandbox helm-lint lint migrate release-check restore-drill test test-browser test-postgres test-temporal typecheck

BACKUP_PATH ?= /private/tmp/workpilot.dump

backup:
	./scripts/backup-postgres.sh $(BACKUP_PATH)

benchmark:
	uv run workpilot-benchmark

build:
	uv build

dev:
	uv run workpilot

eval-safety:
	uv run workpilot-eval --output evals/reports/latest --repetitions 3 --enforce-safety

eval-models:
	uv run workpilot-model-eval --profiles evals/model-profiles.local.json --repetitions 3 --enforce-quality

github-sandbox:
	uv run workpilot-github-sandbox --repository $(WORKPILOT_GITHUB_SANDBOX_REPO)

db-up:
	docker compose -f deploy/docker-compose.yml up -d postgres

db-down:
	docker compose -f deploy/docker-compose.yml down

migrate:
	uv run alembic upgrade head

restore-drill:
	./scripts/restore-drill-postgres.sh $(BACKUP_PATH)

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

release-check: check build
	git diff --check
