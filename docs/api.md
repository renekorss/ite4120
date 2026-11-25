# Frontend API

The local web deployment adds opt-in synthetic code login, English responses, scheduled Web Push and a supplemental synthetic medical registry. Web refreshes retrieve both document types atomically. See the [web guide](web.md) for that deployment. The standalone API defaults below preserve the original password flow.

The React-facing API lives under `/api/v1`. Detailed endpoint descriptions, examples,
security boundaries and the importable frontend Postman collection are described below.

## Canonical API development commands

Run from the repository root. Start Docker first.

```sh
./scripts/init-local.sh
# Install locked local tools (uv is only needed for local development).
uv sync --project api --frozen
# Format and static analysis.
uv run --project api --frozen ruff format --config api/pyproject.toml api/src api/tests scripts/smoke-api.py
uv run --project api --frozen ruff check --config api/pyproject.toml api/src api/tests scripts/smoke-api.py
# Unit checks without infrastructure.
uv run --project api --frozen pytest api/tests/test_domain.py -q
# Unit + real PostgreSQL/mock HTTP integration, in an isolated tmpfs Docker project.
./scripts/test-api.sh
# Existing schema migration/rollback tests.
./scripts/test-database.sh
# Build only after unit/integration gates have passed.
docker compose -f compose.yaml -f compose.mock.yaml -f compose.api.yaml build api
# Start dependencies and migrate local persistence.
docker compose -f compose.yaml -f compose.mock.yaml -f compose.api.yaml up -d --wait postgres xroad-mock
docker compose run --rm liquibase update
./scripts/provision-api.sh
# Start the API.
docker compose -f compose.yaml -f compose.mock.yaml -f compose.api.yaml up -d --wait api
```

Development host/UID settings are written by `init-local.sh` so local non-root
containers can read owner-only bind-mounted secret files. API runtime uses a separate
`reminder_api` login with only `reminder_runtime` grants, not the bootstrap owner or
Liquibase user. `provision-api.sh` is safe to repeat against existing local volumes.

Runtime dependency scan and CycloneDX SBOM (from the complete hash-locked export):

```sh
mkdir -p artifacts
uv run --project api --frozen pip-audit --disable-pip --strict -r api/requirements.lock --progress-spinner off -f cyclonedx-json -o artifacts/api-dependencies.cdx.json
```

## Run with React or Postman

Create optional seeded accounts explicitly after the API stack is running:

```sh
docker compose -f compose.yaml -f compose.mock.yaml -f compose.api.yaml --profile tools run --rm --no-deps api-seed
```

This creates normal `demo.valid`, `demo.expiring`, and other synthetic accounts with
independent random passwords. Passwords are stored only in the owner-only ignored
`.secrets/frontend-api.postman_environment.json` file; no shared password is committed.
Re-running the seed preserves matching credentials. If the file is lost or passwords
were changed, use the same command with `python -m licence_api.seed --output
/seed-output/frontend-api.postman_environment.json --rotate-passwords` appended to
explicitly reset seeded passwords and revoke their existing sessions. Seeding never
runs at normal startup and never creates a public account-selector endpoint.

The API is at **http://127.0.0.1:18080**, interactive Swagger documentation at
**http://127.0.0.1:18080/docs**, and the generated OpenAPI contract at
**http://127.0.0.1:18080/openapi.json**. A version-controlled copy is in
`api/openapi.json`. The API stack automatically runs Liquibase and provisions its
separate runtime role before starting the app. The manual migration/provision steps
above remain useful when diagnosing an existing local volume.

Import [`frontend-api.postman_collection.json`](../postman/frontend-api.postman_collection.json)
into Postman, also import the private `.secrets/frontend-api.postman_environment.json`
file and select that environment. Folders match the API documentation sections.
Send **Authentication → 04 Login with seeded credentials** once: its post-response
script saves `accessToken` as a collection variable. Protected requests inherit the
collection's Bearer authentication and use that token automatically. Keep `accessToken`
out of the environment/global variables so they cannot override the captured value.
After logout or session expiry, send login again.

To test the full workflow, run the entire collection with all requests selected.
A collection post-response script preserves the numbered 24-request sequence across
folders, including validation, logout and upstream-failure checks; manual **Send** only
runs the selected request. Check IDs and subscription IDs are captured automatically.
Set `apiBaseUrl` if you change ports.
The synthetic subscription targets `push.example.test`; no notification is sent.
This is separate from the older collection that directly calls the X-Road mock.
Do not export, cloud-share or commit populated Postman passwords/bearer tokens. The
private environment is a convenience for synthetic local accounts, not a production credential store.

The same requests can be exercised over actual HTTP without Postman:

```sh
python3 scripts/smoke-api.py
```

This checker verifies response statuses and key workflow results, but does not execute
Postman's JavaScript test engine. It modifies only the explicit demo accounts' settings
and sessions. Postman Desktop or its Desktop Agent is needed for localhost access.

React can use ordinary `fetch`; no React-specific backend package is required:

```js
const API_BASE = import.meta.env.VITE_API_BASE_URL;

async function request(path, { token, ...options } = {}) {
  const response = await fetch(`${API_BASE}/api/v1${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) {
    // Display data.error.message and data.error.code; on 401 return to login.
    throw data.error;
  }
  return data;
}

const session = await request("/auth/login", {
  method: "POST",
  body: JSON.stringify({ username: form.username, password: form.password }),
});
const profile = await request("/me", { token: session.accessToken });
const refreshed = await request("/me/driving-data/refresh", {
  method: "POST", token: session.accessToken,
});
const driving = await request("/me/driving-data", { token: session.accessToken });
```

Set React's `VITE_API_BASE_URL=http://127.0.0.1:18080` in its local environment.
Keep the bearer token in memory; never store it in logs, URLs or localStorage. A full
page reload requires login again. The API uses no cookies and the browser does
not attach bearer tokens automatically, so there is no ambient-cookie CSRF flow.
The CORS allowlist defaults to `http://localhost:5173` and `http://localhost:3000`;
add the exact origin if React uses `127.0.0.1` or another port. CORS is not authorization:
all private handlers verify the database-backed bearer session themselves.

Use `expiresAt`/`sessionExpiresAt` and `sessionWarningSeconds` to show an accessible
Estonian expiry warning in React. On expiry/revocation/deactivation the API returns 401.
For the disable-reminders flow, ask for confirmation before sending the PUT request.
For external renewal links, display `externalNotice` before navigation and keep the
URL/fallback instructions visible if opening fails. State-changing endpoints return
JSON/204, not HTML form posts; React handles navigation after success and must not
replay mutations on page reload. Refresh runs only on an explicit action, not render.

## Endpoint contract

All private paths below start with `/api/v1` and require `Authorization: Bearer <token>`.
Responses are camelCase JSON; timestamps are ISO 8601 UTC, source calendar dates are
`YYYY-MM-DD`. Optional unavailable values are `null`, not invented dates.

| Method | Path | Behavior / response |
| --- | --- | --- |
| GET | `/config` | Public `authenticationMode: "password"`, capabilities and session warning interval; push delivery availability is false |
| POST | `/auth/login` | Public `{ "username": "demo.valid", "password": "<generated password>" }`; verifies credentials, returns token, expiry and `dataIsSynthetic` data provenance flag |
| POST | `/auth/logout` | Revoke the current session; 204; subsequent use of that token returns 401 |
| GET | `/me` | Minimal profile/display label and session expiry, never identity-provider claims or personal codes |
| GET | `/me/driving-data` | Status/Estonian explanation, cached licences/categories/certificates, provenance flags, last successful update, latest check and next known deadline |
| POST | `/me/driving-data/refresh` | Synchronous bounded refresh; `{check, data}`. HTTP 200 can contain `check.outcome: "failed"`; show its safe error and retain `data` |
| GET | `/me/status-checks?limit=5` | Newest-first completed/history observations; `{items, limit, hasMore}`; limit 1–50 |
| GET | `/me/status-checks/{checkId}` | Owned check; 404 for missing or another user's record |
| GET | `/me/renewal-guidance` | Relevant action descriptions, official configured URL, external-site notice and fallback message |
| GET | `/me/reminder-preferences` | `enabled`, selected `intervals`, `[90,30,7]` available intervals, update time and delivery capability |
| PUT | `/me/reminder-preferences` | Complete `{enabled, intervals}` replacement; duplicate/unsupported intervals rejected; disable/deselection cancels applicable unsent queued rows |
| GET | `/me/notifications?limit=20` | Sent notifications only, newest first, bounded 1–50; target/date, Estonian text and guidance path; pending/cancelled attempts are not presented as sent |
| POST | `/me/push-subscriptions` | Validate and encrypt browser endpoint/key bundle; idempotent per user/endpoint; returns only subscription ID/timestamps and delivery capability |
| DELETE | `/me/push-subscriptions/{subscriptionId}` | Logically revoke owned subscription, cancel its unsent queue items; 204; cross-user/missing IDs return 404 |

`/health` is an infrastructure endpoint outside the versioned domain API. It checks
PostgreSQL with the runtime connection, but does not report dependency versions or
upstream/internal addresses. No public worker-trigger or arbitrary-person lookup exists.

Reminder example:

```json
{"enabled":true,"intervals":[90,30,7]}
```

Push registration uses the browser's actual `PushSubscription.toJSON()` subset:

```json
{
  "endpoint":"https://push.example.test/example",
  "keys":{"p256dh":"<base64url uncompressed P-256 public key>","auth":"<base64url 16-byte auth secret>"}
}
```

The endpoint's HTTPS hostname must be explicitly allowlisted. The API validates the
P-256 point with the maintained cryptography library, encrypts the complete bundle
using Fernet, and persists only ciphertext and a SHA-256 endpoint fingerprint. It
returns no usable delivery secrets. Re-registering the same endpoint updates the
ciphertext and reactivates the same subscription ID. The example `.test` route is
synthetic and never contacted; change `PUSH_ALLOWED_HOSTS` only for an agreed provider.

Error envelope:

```json
{
  "error": {
    "code":"AUTH_REQUIRED",
    "message":"Seanss puudub või on aegunud. Logi uuesti sisse.",
    "traceId":"00000000-0000-4000-8000-000000000001",
    "fields":[]
  }
}
```

Errors include a safe correlation ID (also `X-Request-Id`). Invalid fields produce
422 without echoing submitted values; missing/expired authentication is 401;
owned-resource mismatches are 404; lock contention is 409; database unavailability
is 503; bodies over 64 KiB are 413; throttled logins return 429 with `Retry-After`. Technical exceptions, SQL, secrets, raw upstream
messages and stack traces never become user responses. The frontend must render
messages as text, not `dangerouslySetInnerHTML`.

## Data integrity and external contract boundaries

The current upstream remains the synthetic HTTP mock from `docs/xroad-mock.md`.
The adapter validates the published source fields, enum values, category membership,
source date ordering, duplicates and bounded response size; source names, personal
codes and document numbers are not cached or returned. Only configured synthetic
identities can be looked up, derived server-side from the logged-in demo account.
It rejects responses not marked by the mock header, to prevent silently using a real
service through this development adapter. A real provider requires an explicit adapter
and identity-resolution design, not merely changing the hostname.

Refreshes use the same account row lock as reminder/subscription writes. Each succeeds
atomically with its new snapshot, or stores a failed check and preserves the previous
successful one. Read-only current assessment also accounts for dates passing since
the snapshot. `statusChanged` compares the persisted result to the previous successful
check, not the current browser rendering. No in-memory background refresh queue exists.

Liquibase **004** adds category issue/expiry dates, `driving_licence.expiry_kind` and an
idempotent subscription endpoint hash. `expiryKind: "driving_right"` identifies the
source's `juhtimisOiguseLoppKp`; it is not falsely labelled proven document expiry.
Category-specific deadlines participate in the next known deadline. No previous
changeset checksum is edited. Existing cache rows default to `expiryKind: "document"`.

A licence-only refresh preserves the most recent independent medical assessment. A required certificate continues to affect the combined driving status, refresh history and reminder eligibility. A newer explicit medical assessment supersedes the earlier one. The source has no medical-certificate expiry. Older cached certificates can still be
shown with their original `cachedAt`, `isCurrent: false` and `nextExpiryIsStale` when
appropriate; they are never copied into a new snapshot as freshly verified data.
Invalid source results similarly omit fresh licence details; older details remain
explicitly marked not current. Always display the warnings and per-document timestamps
in React. A stale/missing observation is not proof of a current legal right to drive.

The 90-day “at risk” threshold is an explicit configurable development assumption,
not an approved legal rule. Assessment uses UTC calendar dates. Confirm the business
timezone, expiry-boundary semantics and thresholds with the product/integration owner
before real data. Failed refreshes, expired snapshots and unknown medical applicability
are distinct states; the UI should not collapse them into a green “everything valid”.

## Authentication and delivery scope

The standalone password route uses normal username/password verification for every account. It never creates
accounts, accepts a persona code, or skips a password check for seeded users. The
`/auth/demo-users` route and `demoUser` login input have been removed. Seeded users are
ordinary credential-backed accounts with synthetic driving data; `dataIsSynthetic`
describes the data, not weaker authentication. Credential provisioning is operator-only;
public registration, password recovery and government eID identity proof are not added.

The `password_credential` table stores normalized usernames, profile labels and salted
Argon2id hashes. `pwdlib[argon2]` uses maintained Argon2 implementations and recommended
cost parameters; the encoded hash includes its algorithm, salt and cost. On successful
verification, hashes are upgraded when library policy requires it. Unknown usernames
still perform a dummy Argon2 verification. Wrong passwords, disabled/deleted accounts
and unknown users return the same generic AUTH_INVALID response, without account hints.
Credentials marked disabled are rejected on every private request, even for a previously
valid token. The runtime can read credentials and upgrade hashes but cannot provision
accounts or change their enabled flag. Do not use a licence number or national ID as a password.

Database-backed throttling applies across API instances to both usernames and socket
source addresses. HMAC-SHA256 identifiers are stored instead of raw usernames/IPs, using
an independent mounted key. Default windows are 300 seconds, allowing five failed
account attempts and 30 source attempts. A successful login clears only its account
bucket; the source limit remains. Blocked requests return 429/Retry-After and are audited.
Expired buckets are removed on subsequent login; production retention must also purge
expired rows during idle periods. Untrusted forwarded-IP headers are ignored. A deployed
trusted proxy needs an explicit source-address/rate-limit design before public access.

Tokens are 256-bit random values; only SHA-256 hashes are stored in `web_session`.
Every private request checks expiry, revocation, credential activation and account
deactivation in PostgreSQL. Logout revokes the current session. Explicit seed-password
rotation revokes all sessions for affected accounts. Migration 005 revokes tokens issued
by the previous picker implementation; rollback deliberately does not reactivate them.
No reusable session identifier is used as a log trace ID. Protect passwords and tokens
with HTTPS before any non-local deployment; the supplied localhost stack uses synthetic
accounts/data and remains development/test only because real X-tee access/deployment
controls are not configured. Actual Estonian identity verification and source mapping
are separate from username/password authentication and remain future integration work.

The API-only configuration stores settings and subscriptions. The web Compose overlay enables VAPID and starts the scheduled sender. Sent history includes provider-accepted reminders and any previously loaded synthetic history. See [web delivery operations](web.md).

## Configuration, operations and dependencies

All values are owned by the deployment maintainer and require service recreation.
The supplied mock-X-Road stack remains development/test only; this is independent
of the password verifier, which is always required.

| Setting | Local value / purpose |
| --- | --- |
| `API_HOST_PORT` | 18080, localhost only |
| `API_UID`, `API_GID` | Generated host UID/GID in ignored `.env`; allows non-root local access to owner-only secret files |
| `APP_ENV` | Development/test mock deployment boundary; there is no authentication-bypass flag |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` | Compose service `postgres`, 5432, configured database, restricted `reminder_api` |
| `DB_PASSWORD_FILE` | Mounted `.secrets/api_password`, generated independently from owner/migrator password |
| `PUSH_KEY_FILE` | Mounted `.secrets/push_key`; random persistent Fernet key, never committed |
| `AUTH_KEY_FILE` | Mounted `.secrets/auth_key`; independent 32-byte HMAC key for short-lived throttle identifiers |
| `LOGIN_MAX_ATTEMPTS`, `LOGIN_SOURCE_MAX_ATTEMPTS`, `LOGIN_WINDOW_SECONDS` | 5, 30 and 300; account/source throttle limits and expiry window |
| `CORS_ORIGINS` | Exact allowed React origins; no wildcard, credentials/cookies disabled |
| `SESSION_SECONDS`, `SESSION_WARNING_SECONDS` | 1800 and 120; absolute expiry, not silently extended on read |
| `RISK_DAYS`, `STALE_SECONDS` | 90 and 86400; proposed development assessment/staleness thresholds |
| `XROAD_BASE_URL`, `XROAD_PATH`, `XROAD_CLIENT` | Explicit local mock service addressing in Compose |
| `XROAD_TIMEOUT_SECONDS` | 3; bounded connections/reads, no automatic retries |
| `DB_POOL_MAX` | 8; bounded shared connections, pool wait 3 seconds, DB connect 3 seconds, lock wait 2 seconds, SQL statement 10 seconds |
| `OFFICIAL_RENEWAL_URL` | Configured official external service address; HTTPS required |
| `PUSH_ALLOWED_HOSTS` | Only `push.example.test` by default for synthetic registration tests; explicit provider allowlist needed later |
| `LOG_LEVEL` | INFO; DEBUG/ERROR can change request diagnostic verbosity; no request body/credential logging at any level |

Dependency purposes: FastAPI/Pydantic provide validated HTTP/OpenAPI contracts; Uvicorn
serves ASGI; psycopg/pool provide parameterized PostgreSQL access and connection reuse;
HTTPX provides bounded upstream HTTP; cryptography implements Fernet and P-256 key
validation. `pwdlib[argon2]` and the MIT-licensed Argon2 bindings provide password
verification and hash upgrades.
Installed package metadata identifies FastAPI/Pydantic as MIT, Uvicorn/HTTPX
as BSD-3-Clause, cryptography as Apache-2.0 OR BSD-3-Clause, and psycopg, its binary
package and connection pool as LGPL-3.0-only. Keep third-party notices and review LGPL
distribution obligations before publishing an image. Exact versions/hashes and
transitive dependencies are in `api/uv.lock` and hash-locked runtime/development requirements. Test tooling is pytest/coverage, Ruff and
pip-audit. No custom cryptographic algorithm is implemented. The Python base image is
digest-pinned; production OS/image scans and deployment approvals are still required.

Startup order: PostgreSQL health → Liquibase update → owner-only local runtime-role
provisioning → API health. Only the short-lived `api-db-init` service sees owner
credentials. The API sees only its runtime password, encryption key and independent throttle key.
The optional short-lived `api-seed` operator command uses owner credentials for provisioning. Runtime source
is read-only, non-root, without Linux capabilities; no TLS termination is provided by
the local Compose demo. Use only synthetic data over localhost HTTP. Production needs
TLS, independent secret provisioning, vault-backed key rotation and least-privilege
operational roles as already recorded in database exceptions E-01–E-05.

Routine output is one JSON event per request with UTC timestamp, method, outcome,
safe error code (or null) and random trace ID. That per-operation trace UUID is
also sent as `X-Road-Id` and persisted even for failed refreshes, so source and
application events can be correlated without logging request payloads. Raw URL paths, IPs, request bodies, sessions, tokens, subscription
endpoints and full source payloads are omitted. Uvicorn access logs are disabled.
Audit records cover successful/failed login, logout, protected-access denials, profile/
cache/history/guidance reads, refresh results, preference changes and subscription
registration/revocation. Local state changes and their audit writes commit together.
The existing independent administrator audit and retention-job requirements remain
unresolved; passing API tests does not establish full ASVS/TEHIK production compliance.

Do not overwrite `.secrets/push_key`: existing subscriptions depend on it. Current
`local-fernet-v1` is a single development key; production rotation needs a vault and
versioned key-ring/decryption strategy. Local runtime password changes must be paired
with role provisioning and API restart. Expired sessions/cache/subscriptions still
need the retention operations already proposed in `docs/database.md`.

For diagnosis use `docker compose -f compose.yaml -f compose.mock.yaml -f compose.api.yaml logs api`.
Stop the full stack with the same file list and `down` (no volume-deletion flag).
Recovery for a failed migration remains forward correction or verified backup restore;
004 rollback removes its new fields and must not be run on populated real environments
without an approved recovery plan. No data is automatically deleted at API startup.

## Story and requirement verification

| Story | API implementation / automated evidence |
| --- | --- |
| US-01/02 | Verified password login for normal/seeded users, Argon2 hashes, shared throttling, database-backed sessions, logout/expiry/deactivation; tests in `test_api.py` and `test_password_auth.py`; government eID/source identity proof remains separate |
| US-03/04 | Profile and minimized driving data with status, category dates, document provenance and next known deadline; source normalization and stale-medical tests |
| US-05/13 | Synchronous refresh, preserved successful snapshot on failure, status comparison and bounded owned history; real PostgreSQL/mock HTTP integration tests, timeout recovery |
| US-06/07 | Relevant Estonian guidance and configured official hand-off notice/fallback; frontend opening/keyboard flow awaits React |
| US-08/09/11 | Owned validated reminder settings, default disabled state, cancellation of unsent reminders, encrypted idempotent/revocable subscription persistence; actual permission/confirmation/delivery UX remains frontend/worker scope |
| US-10 | Sent-only owned newest-first notification history, frozen dates and guidance path; integration tests ensure cancelled/pending records are excluded |
| US-12 | API can persist settings and cancel obsolete queued rows; scheduler/delivery not claimed; capability is explicitly false |

Applicable requirements are traced through `api/src/licence_api/` to the unit and
integration tests: UTC, synthetic data, minimized caches, bound SQL, role separation,
server authorization, safe Estonian errors, correlation/audit, configurable timeouts,
stateless sessions and explicit settings. CORS preflight is tested for allowed and
untrusted origins; no React UI has been changed, so keyboard/assistive-technology and
browser E2E tests await that implementation. Real X-tee interface/load/resilience gates
must still run against the agreed connected systems before release.

## Verification record — 2026-11-12

- Ruff formatting/static analysis passed using the locked tools.
- The pre-password revision passed 47 tests with 95% coverage. After password
  authentication replaced the picker, 67 tests passed against real disposable
  PostgreSQL and the HTTP mock with 96% statement coverage; authentication and
  configuration modules have 100% statement coverage.
  The suite includes rejection of cross-user record access, session revocation/expiry,
  stale cache preservation, encrypted/idempotent subscriptions, CORS, payload limits,
  date progression and automatic pool recovery after idle connections are terminated.
- A test-only Starlette warning notes a future TestClient transport migration;
  no test is skipped or suppressed. Runtime HTTPX integration uses the current client.
- `./scripts/test-database.sh`: all five changesets validated through fresh install,
  repeated update and complete rollback/reapplication; existing SQL/demo checks passed.
- `python3 scripts/smoke-api.py`: all 23 frontend collection requests passed against
  the built local API over HTTP, including expected 401/422/204 and upstream-failure flows.
- Runtime pip-audit found no known vulnerabilities and produced a CycloneDX inventory.
  This does not replace container OS/image scanning or guarantee absence of vulnerabilities.
- SPDX inventories were generated for the built API and dependency images. Docker Scout
  vulnerability scanning remains blocked by its Docker login requirement; no clean
  container OS scan is claimed.

No real identity provider, live X-tee service, React browser UI, sender, retention job,
full ASVS audit, approved load target or production deployment was exercised. The API
is ready for local React/Postman development with credential-backed accounts and the
explicit synthetic-source/deployment constraints above.

## Password authentication update

Migration 005 adds `password_credential` and `login_throttle`; both have documented
primary keys, constraints and purpose/retention boundaries. Credentials persist only
for the account lifetime and cascade on approved account purge; only credential hashes,
not passwords, enter database backups. Throttle records are short-lived pseudonymous
data, accessible only to the runtime and authorised retention operator. The private
seed environment contains usable test passwords and must stay owner-only and ignored
by version control. Remove it when the local environment is retired, and never include
it in packages, screenshots or public Postman workspaces. The new dependency's license
metadata and vulnerability scan are recorded with the locked requirements/SBOM.

The older verification record describes the pre-password revision. Updated checks
specifically cover mandatory passwords, unknown/disabled users, removed picker routes,
Argon2 storage and upgrades, account/source throttles, forged forwarded-IP headers,
private seed output, idempotent seeding, explicit password rotation and token revocation.

Current authentication verification: 67 API tests passed at 96% statement coverage;
all five migrations passed rollback/reapplication, and the updated Argon2 dependency
scan found no known vulnerabilities. Actual operator seed output and the credential-
backed Postman workflow are also checked against the built local service. No passwords
are printed, committed or included in the package. Existing production infrastructure,
identity-to-registry proof and notification-delivery limitations remain separate.

Postman usability change request → versioned-interface documentation and credential
handling requirements → tagged folders, inherited Bearer authentication and runner
ordering in `postman/frontend-api.postman_collection.json` → repository artifact checks,
JavaScript script checks and `scripts/smoke-api.py`. No API, migration or security-policy
change is required.

Driving-data reads and refreshes include `renewalActions`. Each action identifies
the document card that offers renewal guidance (`renew_licence` or `renew_medical`).
The guidance endpoint uses the same actions and configured risk window. An empty
list means neither card has a renewal deadline in that window. US-04/06 traceability:
`driving_data` in main.py, LicencePage, test_card_actions_match_guidance and the
desktop/mobile renewal navigation checks in web.spec.ts.
