#!/bin/sh
# Explicit local-only loading; never called by migrations or application startup.
set -eu
docker compose exec -T postgres sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < database/fixtures/demo.sql
