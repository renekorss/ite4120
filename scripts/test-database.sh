#!/bin/sh
# Dedicated disposable project; never points at the developer database project.
set -eu
./scripts/init-local.sh
test_directory=$(mktemp -d /tmp/licence-reminder-test.XXXXXXXX)
test_project=$(basename "$test_directory" | tr '[:upper:].' '[:lower:]-')
compose() { docker compose -p "$test_project" -f compose.yaml -f compose.test.yaml "$@"; }
cleanup() { compose down; rmdir "$test_directory"; }
trap cleanup EXIT HUP INT TERM
compose up -d --wait postgres
compose run --rm liquibase validate
compose run --rm liquibase update
compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tests/integration.sql'
compose run --rm liquibase update
compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1 / (CASE WHEN count(*) = 3 THEN 1 ELSE 0 END) FROM databasechangelog"'
compose run --rm liquibase rollback-count --count=3
compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tests/after-rollback.sql'
compose run --rm liquibase update
compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tests/integration.sql'
