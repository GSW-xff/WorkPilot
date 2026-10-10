#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 ABSOLUTE_BACKUP_PATH" >&2
  exit 64
fi

backup_path="$1"
if [[ "$backup_path" != /* ]]; then
  echo "backup path must be absolute" >&2
  exit 64
fi

backup_parent="${backup_path%/*}"
mkdir -p "$backup_parent"

compose_file="deploy/docker-compose.yml"
backup_user="${WORKPILOT_BACKUP_DATABASE_USER:-postgres}"
docker compose -f "$compose_file" exec -T postgres \
  pg_dump \
    --username="$backup_user" \
    --dbname=workpilot \
    --format=custom \
    --no-owner \
    --no-acl >"$backup_path"

if [[ ! -s "$backup_path" ]]; then
  echo "backup is empty: $backup_path" >&2
  exit 1
fi

bytes="$(wc -c <"$backup_path" | tr -d ' ')"
checksum="$(shasum -a 256 "$backup_path" | awk '{print $1}')"
echo "backup_path=$backup_path"
echo "backup_bytes=$bytes"
echo "backup_sha256=$checksum"
