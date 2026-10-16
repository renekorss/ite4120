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
