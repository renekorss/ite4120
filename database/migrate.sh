#!/bin/sh
set -eu
export LIQUIBASE_COMMAND_PASSWORD="$(cat /run/secrets/postgres_password)"
exec /liquibase/liquibase "$@"
