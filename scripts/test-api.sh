#!/bin/sh
# Use a new project with tmpfs storage; never delete an existing database volume.
set -eu
./scripts/init-local.sh
test_directory=$(mktemp -d /tmp/licence-api-test.XXXXXXXX)
test_project=$(basename "$test_directory" | tr '[:upper:].' '[:lower:]-')
compose() { docker compose -p "$test_project" -f compose.yaml -f compose.mock.yaml -f compose.api.yaml -f compose.test.yaml -f compose.api-test.yaml "$@"; }
cleanup() { compose down; rmdir "$test_directory"; }
trap cleanup EXIT HUP INT TERM
compose up -d --wait postgres xroad-mock
compose run --rm liquibase update
cat .secrets/api_password database/provision-api.sql | compose exec -T postgres sh -c '
  IFS= read -r API_DATABASE_PASSWORD
  export API_DATABASE_PASSWORD
  exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
'
compose run --rm --no-deps api-test
