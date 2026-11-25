#!/bin/sh
set -eu
umask 077
mkdir -p .secrets
if [ ! -f .secrets/postgres_password ]; then
  openssl rand -hex 32 > .secrets/postgres_password
fi
if [ ! -f .env ]; then
  cp .env.example .env
fi
# Independent runtime credentials; keep the bootstrap/migration secret separate.
if [ ! -f .secrets/api_password ]; then
  openssl rand -hex 32 > .secrets/api_password
fi
if [ ! -f .secrets/push_key ]; then
  openssl rand -base64 32 | tr '/+' '_-' > .secrets/push_key
fi
# Let local non-root containers read owner-only bind-mounted development secrets.
if ! grep -q '^API_UID=' .env; then
  printf '\nAPI_UID=%s\n' "$(id -u)" >> .env
fi
if ! grep -q '^API_GID=' .env; then
  printf 'API_GID=%s\n' "$(id -g)" >> .env
fi
if [ ! -f .secrets/auth_key ]; then
  openssl rand -hex 32 > .secrets/auth_key
fi
if [ ! -f .secrets/vapid.pem ]; then
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out .secrets/vapid.pem
fi
# Pin synthetic medical dates across restarts and repeated licence refreshes.
if ! grep -q '^MOCK_MEDICAL_REFERENCE_DATE=' .env; then
  printf 'MOCK_MEDICAL_REFERENCE_DATE=%s\n' "$(date -u +%F)" >> .env
fi
