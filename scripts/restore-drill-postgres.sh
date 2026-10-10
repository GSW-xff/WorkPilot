#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 ABSOLUTE_BACKUP_PATH" >&2
  exit 64
fi

backup_path="$1"
if [[ "$backup_path" != /* || ! -s "$backup_path" ]]; then
  echo "backup must be a non-empty file at an absolute path" >&2
  exit 64
fi

compose_file="deploy/docker-compose.yml"
drill_database="workpilot_restore_drill"

cleanup() {
  docker compose -f "$compose_file" exec -T postgres \
    dropdb --username=postgres --if-exists "$drill_database" >/dev/null
}
trap cleanup EXIT

cleanup
docker compose -f "$compose_file" exec -T postgres \
  createdb --username=postgres --owner=workpilot_owner "$drill_database"
docker compose -f "$compose_file" exec -T postgres \
  psql --username=postgres --dbname="$drill_database" \
    --command="CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
docker compose -f "$compose_file" exec -T postgres \
  pg_restore \
    --username=workpilot_owner \
    --dbname="$drill_database" \
    --no-owner \
    --no-acl \
    --no-comments <"$backup_path"

source_tables="$(
  docker compose -f "$compose_file" exec -T postgres \
    psql --username=workpilot_owner --dbname=workpilot --tuples-only --no-align \
    --command="SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
)"
restored_tables="$(
  docker compose -f "$compose_file" exec -T postgres \
    psql --username=workpilot_owner --dbname="$drill_database" --tuples-only --no-align \
    --command="SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
)"
restored_alembic="$(
  docker compose -f "$compose_file" exec -T postgres \
    psql --username=workpilot_owner --dbname="$drill_database" --tuples-only --no-align \
    --command="SELECT count(*) FROM alembic_version;"
)"

if [[ "$source_tables" -lt 1 || "$restored_tables" != "$source_tables" ]]; then
  echo "table-count verification failed: source=$source_tables restored=$restored_tables" >&2
  exit 1
fi
if [[ "$restored_alembic" != "1" ]]; then
  echo "alembic metadata verification failed: rows=$restored_alembic" >&2
  exit 1
fi

echo "restore_database=$drill_database"
echo "source_tables=$source_tables"
echo "restored_tables=$restored_tables"
echo "alembic_rows=$restored_alembic"
echo "restore_verification=passed"
echo "cleanup=automatic"
