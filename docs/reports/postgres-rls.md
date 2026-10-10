# PostgreSQL RLS adversarial verification

The integration suite in `tests/test_postgres_rls_integration.py` runs migrations as the
non-application owner and all attacks as the unprivileged `workpilot_app` role. It checks:

- no tenant context produces zero visible parent, child and outbox rows (default deny);
- tenant A cannot read tenant B even with an explicit tenant predicate;
- parent rows, child rows and outbox rows expose only the active tenant;
- a cross-tenant update matches zero rows;
- rewriting a visible row's `tenant_id` is rejected by `WITH CHECK`;
- all nine tenant-bearing or task-child tables have both RLS and FORCE RLS enabled.

Run `make db-up`, migrate using `workpilot_owner`, then run `make test-postgres`. The test
is gated by `WORKPILOT_RUN_POSTGRES_INTEGRATION=1` so the normal offline suite remains
deterministic. A passing run must use real PostgreSQL; SQLite results are not accepted as
evidence for this report.

## Verified run

- Date: 2026-10-10
- Database: `pgvector/pgvector:pg16` under Docker Desktop 29.7.2
- Result: `3 passed`
- Roles: migrations as `workpilot_owner`; adversarial queries as `workpilot_app`

The GitHub Actions `postgres-rls` job provisions the same unprivileged role and reruns this
suite on every push and pull request.
