# Database verification evidence

Verified on 2026-10-15 using Docker Engine 29.8.1, Compose v5.5.1, Python 3.11.6,
PostgreSQL 17.11 and Liquibase Community 4.33.0. Image digests are pinned in
`compose.yaml` and `.env.example`. All fixture identities are fabricated. No backend,
frontend, production data or live X-Road system was used.

| Command / gate | Observed result |
| --- | --- |
| `python3 -m unittest discover -s database/tests -p 'test_*.py' -v` | 4 tests passed: changelog/rollback references, all story IDs mapped, shell syntax, text hygiene |
| `docker compose config --quiet` | Passed |
| `docker compose -f compose.yaml -f compose.test.yaml config --quiet` | Passed; test PostgreSQL data uses tmpfs |
| `./scripts/test-database.sh` | Passed in a fresh randomly named project; 45 SQL assertions passed on both initial installation and rollback/reapplication |
| Liquibase `validate` within test runner | Passed |
| First `update` | 3 changesets applied |
| Repeated `update` | 0 changesets applied; 3 previously applied, checksums retained |
| `rollback-count --count=3` | Passed; catalog check confirmed application tables removed |
| Update after rollback | All 3 changesets reapplied; same SQL assertions passed |
| Local persistent Compose database | Started healthy; migration update succeeded; `status --verbose` reported up to date |
| `git diff --check` | Passed |
| `./scripts/scan-images.sh` | Blocked: Docker Scout requires Docker login. Exit 1; no vulnerability clearance claimed. Direct attempts for both image tags returned the same authentication requirement |
| `./scripts/sbom-images.sh` | Passed without login by indexing local images; SPDX JSON generated for both pinned images under ignored `artifacts/` |
| SBOM JSON parsing | Both files parsed successfully as SPDX documents |
| `./scripts/package-database.sh` | Created deterministic source archive and SHA-256 checksum under ignored `artifacts/`; checksum verified |

Database assertions cover duplicate identity, session hash/date validation and revocation;
failed refresh retaining the successful snapshot; a newer successful changed status;
non-valid status requiring a reason; cache references rejecting failed checks; unique
categories and issue/expiry validation; earliest known document deadline; opt-in default
and supported intervals; same-user notification/target/subscription ownership; target
expiry agreement; semantic notification deduplication; delivery state/timestamp shape;
failed-attempt error requirement; persisted cancellation and sent history; snapshot
retention while notifications reference it; runtime DDL/migration-metadata/cache deletion
denial; insert-only runtime audit access and auditor/retention separation; audited account
purge and cascades; all FK indexes; all schema/table/column comments; Estonian collation
case/accent behavior; and UTC database time. These are database checks, not evidence
that future authentication, workers, browser permissions or external APIs work.

The test runner stops only its newly generated project. Its database data is temporary;
it never issues `down --volumes`. The regular local `ite4120` Compose database is left
running with an empty application schema (no test users persisted). Generated secret
files, scan output, SBOMs and packages are ignored by Git. The packaged source excludes
secrets, caches and generated artifacts.

No application build, general SQL formatter/linter, frontend accessibility, end-to-end,
real interface, provider resilience or representative load suite exists yet. Packaging
is the build artifact for this increment. Unit coverage percentages are not claimed for
SQL; coverage/release/workload targets must be agreed before first release. Future
services must implement the documented transactional and authorization rules and add
their own positive and failure-path tests.

Production blockers are documented in `docs/database.md` (E-01–E-05): PostgreSQL
portability approval, independent privileged audit protection/IdP audit scope, deployment
TLS and credential separation, vulnerability clearance, and integrity classification.
Retention periods, X-Road contracts/status mappings, delivery semantics and key management
need agreement before processing real data. None of those approvals is implied by the
passing synthetic-data migration tests.

## PR preparation — 2026-10-16

After enabling the local TablePlus port, `compose.test.yaml` now explicitly resets
host ports so the test database can run alongside the local database. Resolved Compose
configuration confirmed no test port mapping. The 4 repository checks, 45 database
assertions before and after rollback/reapplication, migration idempotency, and
`git diff --check` passed again. Packaging and checksum verification were repeated.
