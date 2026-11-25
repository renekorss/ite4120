#!/bin/sh
# Local development bootstrap only; production provisions independent login roles.
set -eu
./scripts/init-local.sh
cat .secrets/api_password database/provision-api.sql | docker compose exec -T postgres sh -c '
  IFS= read -r API_DATABASE_PASSWORD
  export API_DATABASE_PASSWORD
  exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
'
