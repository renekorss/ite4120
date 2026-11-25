#!/bin/sh
# Start the local API, worker, and web frontend with synthetic accounts.
set -eu
cd "$(dirname "$0")/.."
./scripts/init-local.sh
compose() { docker compose -f compose.yaml -f compose.mock.yaml -f compose.api.yaml -f compose.web.yaml "$@"; }
compose up --build -d --wait api
compose --profile tools run --rm --no-deps api-seed
compose exec -T api python -m licence_api.demo
compose up -d --wait worker
api_address=$(compose port api 8000)
export API_PROXY_TARGET="${API_PROXY_TARGET:-http://$api_address}"
cd frontend
npm ci
exec npm run dev -- --host 127.0.0.1 "$@"
