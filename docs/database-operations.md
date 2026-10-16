# Database operations and contributor commands

Local PostgreSQL is reachable at `127.0.0.1:5432` for tools such as TablePlus.
The isolated test database publishes no host port.
`init-local.sh` generates an ignored random secret and copies `.env.example` once.
It never overwrites an existing secret. Compose secrets are file mounts, not a vault.
The local owner and migrator share this generated secret solely to simplify development;
production must provision independent credentials and TLS before handling real data.
The owner is used for bootstrap/tests; Liquibase authenticates as the non-superuser `migrator`.
Runtime/auditor/retention roles are NOLOGIN capability roles: production creates distinct
login identities and grants the appropriate capability, never `migrator` membership.

## Canonical checks

Run these gates before packaging, in order. Tests use fabricated data only.

| Check | Command / scope |
| --- | --- |
| Format / static repository checks | `python3 -m unittest discover -s database/tests -p 'test_*.py' -v` (XML references, rollbacks, story coverage, whitespace; no general SQL formatter configured) |
| Shell syntax | Same Python unittest command (runs `sh -n` separately for every shell script) |
| Compose validation | `docker compose config --quiet` and `docker compose -f compose.yaml -f compose.test.yaml config --quiet` |
| Unit checks | Same Python unittest command; no application logic exists to unit-test |
| Integration / migration / DB permissions | `./scripts/test-database.sh` |
| Build/package | `./scripts/package-database.sh` after the preceding checks pass |
| Dependency/security scan | `./scripts/scan-images.sh` (requires Docker Scout authentication; nonzero blocks release) |
| SBOM | `./scripts/sbom-images.sh` (local image indexing; emits SPDX JSON) |
| Local run | `docker compose up -d --wait postgres` then `docker compose run --rm liquibase update` |
| End-to-end / accessibility / interface | Not applicable to this database-only increment; implement with future web/API flows and real X-Road test connection |
| Resilience / load | Migration reapply and rollback are exercised now; application retry, external outage and measured sprint-end load gates await a running service and agreed targets |

The test script uses a fresh generated Compose project and tmpfs for PostgreSQL data.
It validates, migrates, tests, re-runs update (no new changesets), rolls back all three
changesets, reapplies and tests again. Cleanup stops only that generated project;
no volume-deletion command is used. The ordinary local project's data persists.
The tests also run inside the PostgreSQL container and need no Python dependencies.
A GitLab runner can invoke the same commands with a reachable Docker daemon; no CI
pipeline or production deployment is claimed in this increment.

## Configuration

All settings are owned by the deployment maintainer. Change before creating the
containers; recreating services is required. Changing initial database/owner/password
settings does **not** change an existing PostgreSQL volume: rotate credentials through
an authorised SQL operation and update the mounted secret together.

| Setting | Safe local default / purpose |
| --- | --- |
| `POSTGRES_DB` | `licence_reminder`; database name, simple SQL identifier |
| `POSTGRES_USER` | `database_owner`; local bootstrap owner, simple SQL identifier |
| `POSTGRES_PASSWORD_FILE` | `./.secrets/postgres_password`; required generated secret file, never committed |
| `POSTGRES_IMAGE` | PostgreSQL 17.11 bookworm, exact manifest digest in Compose and `.env.example` |
| `LIQUIBASE_IMAGE` | Liquibase 4.33.0, exact manifest digest in Compose and `.env.example` |
| `LIQUIBASE_COMMAND_URL` | Composed from internal service name and database name; production supplies its own JDBC URL and TLS settings |
| `LIQUIBASE_COMMAND_USERNAME` | Local `migrator`; production independently provisioned migration identity |
| `LIQUIBASE_COMMAND_PASSWORD` | Read at container startup from the secret, never passed as a command-line argument |
| `TZ`, `PGTZ`, PostgreSQL `timezone` | UTC, fixed in local Compose |

There are no committed connection credentials, personal data, environment-specific
external addresses or runtime login passwords. No package-manager dependencies or
lockfile are needed; the two container images are pinned by immutable digest.
PostgreSQL uses its PostgreSQL licence; Liquibase 4.33.0 Community uses Apache-2.0
and includes the JDBC driver. Liquibase 5 changes licensing and driver packaging;
review a future upgrade explicitly. Scout inventories transitive OS/JVM/JDBC packages
in the per-image SPDX SBOM. Image updates must rerun the same gates.

## Migration, operations and recovery

The ordered entry point is `database/changelog/db.changelog.xml`. Never edit an
already deployed changeset: append a new numbered changeset, documenting data
migration and compatibility. Liquibase records checksums and serializes migrations
using its lock table. Migration runs finish before future application startup.
The bootstrap script runs only on first initialization; roles must already exist and the migrator must own the application schema
when using an externally provisioned database. No `drop-first` option is used.

```sh
# Stop local services while keeping the developer database.
docker compose down
# Inspect database diagnostics (no SQL statement/parameter logging).
docker compose exec postgres sh -c 'cat /var/lib/postgresql/data/current_logfiles'
# Backup before a material migration; protect this ignored artifact as personal data.
mkdir -p artifacts
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > artifacts/database.dump
# Restore only into an independently provisioned recovery database with matching roles:
# pg_restore --exit-on-error --no-owner --dbname=<recovery database> artifacts/database.dump
```

PostgreSQL writes structured JSON diagnostics under the paths reported by
`current_logfiles`; rotate/ship with the production logging platform. SQL statements
and bind values are suppressed, but server messages can still contain key values:
restrict access, review/redact production diagnostics, and never forward raw database
errors to users. Liquibase container logs are deployment diagnostics, not ECS audit
records. Application JSON/ECS event emission awaits the backend.

Rollback SQL exists for clean development databases and is automatically tested.
`docker compose run --rm liquibase rollback-count --count=3` **destroys the entire
application schema**; use only in an explicitly disposable empty environment.
For populated environments, prefer a forward corrective migration or restore a
verified backup under the deployment owner's procedure. Never clear checksums or
force-release a lock unless an authorised operator has verified that no migration
is running. No production backup schedule, deletion job or reminder worker is installed.
