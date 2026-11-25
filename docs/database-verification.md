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

## Synthetic demo data — 2026-10-16

Added optional fixtures for seven driving scenarios, documented in `docs/demo-data.md`.
`./scripts/test-database.sh` passed the existing migration/rollback assertions and
12 demo assertions after both initial fixture loading and repeat loading. The repeat
load skipped insertion as intended. The 4 repository checks, `git diff --check`, source
packaging and checksum verification passed. `./scripts/seed-demo.sh` loaded the fixtures
into the local database; the same 12 demo assertions passed there. No schema migration,
real registry call, usable authentication secret or actual notification delivery was added.

## Upstream HTTP mock — 2026-10-16

The public ee-test `juhilubaKehtivus` v1 contract was retrieved and a structural
snapshot with source checksum recorded under `mocks/xroad/contracts/`. The optional
mock is independent of SQL fixture rows. All 15 contract/HTTP checks passed in the
pinned Python container, including injected timeout recovery; 4 repository checks
and whitespace checks passed. The initial host HTTP checks were blocked by sandbox
socket permissions, so the full suite ran successfully in Docker. The mock's Compose
configuration validated, its health check passed, and the documented curl request
returned synthetic JSON on localhost port 18081. Port 8081 was occupied by another
project and was left unchanged. SPDX generation including Python succeeded;
Docker Scout vulnerability scanning still requires authentication. Source packaging
and SHA-256 verification passed. No real X-Road request or database migration occurred.
See `docs/xroad-mock.md` for contract limitations and canonical run/test commands.

## React-facing API — 2026-11-12

Added the FastAPI frontend contract, restricted runtime login, migration 004, isolated
API integration harness and separate 23-request frontend Postman collection. The API
suite passed 47 tests with 95% statement coverage using real PostgreSQL and HTTP mock
collaboration. Tests cover source validation, authorization/ownership, session expiry/
revocation, reminder state, old medical-data provenance, encrypted subscriptions,
CORS, safe errors/logs, date progression and recovery after idle DB connections die.
All four migrations passed fresh install, repeated update and rollback/reapplication;
existing SQL/demo checks passed. Formatting/static analysis passed. Runtime dependency
pip-audit found no known vulnerabilities and generated a CycloneDX inventory.

The image built successfully and the local startup chain ran migrations and runtime
role provisioning before API health passed. All 23 frontend collection requests passed
over HTTP against the built service; the OpenAPI contract was exported to `api/openapi.json`.
This smoke checker does not execute Postman's JavaScript engine or a React browser.
SPDX inventory generation succeeded; container vulnerability scanning still requires
Docker Scout authentication. Reproducible source packaging/checksum verification is
recorded alongside the artifact. No real identity provider, live X-tee interface,
notification delivery, browser accessibility/E2E or production load gate is claimed.
See `docs/api.md` for full commands, traceability, source limitations and release blockers.

## Verified password authentication — 2026-11-12

Replaced the picker with normal username/password verification. Public account listing
and `demoUser` inputs are removed; no account is created by login. Argon2id credential
storage, automatic hash upgrades, shared account/source throttling, generic failures
and disabled-account checks are exercised by 67 API tests at 96% statement coverage.
All five migrations passed installation, idempotency and rollback/reapplication;
migration 005 revokes and audits earlier picker sessions without reactivating them
on rollback. Runtime dependency scanning including Argon2 found no known vulnerabilities.

The rebuilt image started successfully. The optional operator seed was invoked
explicitly and generated owner-only private Postman credentials. All 23 frontend
collection requests passed over HTTP using actual username/password verification.
The published OpenAPI requires username/password and has no demo-user-list route.
Seed idempotence, password rotation/revocation, private output permissions and absence
of passwords in error responses/logs are tested. Inventory/package/checksum gates were
refreshed. No private Postman environment or passwords are included in source control
or the package. The X-Road data remains synthetic; live source identity proof and
production deployment controls remain separate from credential verification.
