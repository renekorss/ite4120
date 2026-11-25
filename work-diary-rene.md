# Work Diary - Rene Korss

## 2026-09-28
*Hours:* 3 hours
*Work*
- Create GitHub repo and initial files
- Install and configure docker
*Corrections:* None
*Evidence:* None

## 2026-09-30
*Hours:* 6 hours
*Work*
- Group discussion and ideation for the feature
- Created initial ideas for different possible services
*Corrections:*
- Agreed on a service to build and user stories to create
*Evidence:*
- Whatsapp chat discussion
- Feature definition `README.md`

## 2026-10-01
*Hours:* 3 hours
*Work*
- Read TEHIK development guidelines at https://www.tehik.ee/arendusjuhendid
*Corrections:* None
*Evidence:* None

## 2026-10-02
*Hours:* 6 hours
*Work*
- Created user stories
- Created pull request with user stories and update to work diary
- Reviewed other users pull requests
*Corrections:*
- More user stories
*Evidence:*
- Updated file: `user-stories.md`
- Updated file: `work-diary-rene.md`

## 2026-10-15
*Hours:* 2 hours
*Work*
- Reviewed all Driving Licence Reminder user stories and acceptance criteria for database persistence requirements
- Designed a normalized PostgreSQL schema with 12 tables covering accounts, sessions, driving data, reminder settings, notifications and audit events
- Implemented three version-controlled Liquibase changesets and Docker Compose setup
- Documented the Mermaid ERD, user-story mapping, retention proposal, security boundaries and decisions awaiting X-Road contracts
- Verified migrations, repeated updates, rollback and reapplication, with 45 database assertions
- Generated image SBOMs and a database source package with a verified SHA-256 checksum
*Corrections:*
- Changed migration tests to use a unique Docker project and temporary database storage
- Added database schema, table and column comments following the TEHIK requirements
- Recorded vulnerability scanning as incomplete because Docker Scout requires authentication
*Evidence:*
- Schema and migrations: `database/changelog/`
- Docker setup: `compose.yaml`, `compose.test.yaml`
- Automated checks: `database/tests/`, `scripts/test-database.sh`
- Design and traceability: `docs/database.md`, `docs/database-erd.mmd`
- Verification results and unresolved production requirements: `docs/database-verification.md`

## 2026-10-16
*Hours:* 1 hour
*Work*
- Shortened the README to local setup, startup, database access and shutdown instructions
- Moved detailed operational and testing instructions into a separate document
- Exposed PostgreSQL on localhost and successfully connected through TablePlus
- Investigated X-Road Playground services and their limitations for driving-licence data
- Located the public ee-test juhilubaKehtivus OpenAPI contract and implemented a local HTTP mock with contract-shaped responses and failure scenarios
- Added clearly marked synthetic driving scenarios, reminders and history for local database exploration
*Corrections:*
- Removed the trailing newline when copying the database password for TablePlus
- Added the missing diary entries for the database homework
- Isolated test database ports from the local TablePlus connection before creating the pull request
*Evidence:*
- Setup instructions: `README.md`
- Operations and test commands: `docs/database-operations.md`
- Local database port mapping: `compose.yaml`
- TablePlus connection confirmed working
- Synthetic fixture data and provenance: `database/fixtures/demo.sql`, `docs/demo-data.md`
- HTTP mock contract, usage and tests: `mocks/xroad/`, `compose.mock.yaml`, `docs/xroad-mock.md`

## 2026-11-12
*Hours:* ~6 hours
*Work*
- Reviewed the HTTP mock against the public X-tee test contract and confirmed the source checksum was unchanged
- Added an importable Postman collection with ten synthetic request scenarios and response assertions
- Implemented the React-facing FastAPI API for demo sessions, profiles, driving data and refresh, reminder settings, guidance, notifications and browser subscription storage
- Added Liquibase migration 004 for source category dates, deadline provenance and subscription deduplication
- Documented React integration and created a separate frontend Postman collection with 23 requests
- Verified restricted-role database access, ownership, CORS, session revocation, failure recovery and encrypted subscription persistence
- Replaced account-picker login with normal username/password verification, Argon2id hashes, database-backed throttling and separately seeded test accounts
- Removed the public demo-user selector and added migration 005 to revoke earlier picker sessions
- Updated Postman to use private generated credentials and verified password rotation and seed-file permissions
- Grouped frontend Postman requests by API documentation section, documented automatic token reuse and preserved the full verification workflow across folders
*Corrections:*
- Clarified that the collection covers the upstream mock rather than the future frontend-facing API
*Evidence:*
- Postman collection: `mocks/xroad/postman/xroad-mock.postman_collection.json`
- Import instructions: `docs/xroad-mock.md`
- Frontend API, OpenAPI and automated checks: `api/`
- Frontend API guide and Postman collection: `docs/api.md`, `postman/frontend-api.postman_collection.json`
- API Compose stack and verification commands: `compose.api.yaml`, `scripts/test-api.sh`, `scripts/smoke-api.py`

## 2026-11-22
*Hours:* ~3 hours
*Work*
- Reviewed the cached Figma screens and built the English React and TypeScript login, Overview and Licence views.
- Connected all three sign-in choices to the same synthetic demo accounts so testers could switch between licence scenarios.

*Evidence:* [Login](frontend/src/login.tsx), [Overview and Licence](frontend/src/main.tsx), [demo accounts](docs/web.md#test-accounts).

## 2026-11-23
*Hours:* ~3 hours
*Work*
- Connected reminder preferences to browser notification permission and subscription registration.
- Implemented scheduled Web Push delivery and checked that a reminder could appear with the app tab closed. Verified that turning reminders off stops future deliveries.

*Evidence:* [Reminder settings](frontend/src/reminders.tsx), [delivery worker](api/src/licence_api/delivery.py), [service worker](frontend/public/sw.js).

## 2026-11-24
*Hours:* ~3 hours
*Work*
- Investigated why refreshing demo account 00000000007 appeared to clear its medical warning. Checked that refresh reads both registries and keeps the last successful data when a lookup fails.
- Matched the mobile menu and reminder confirmation to the design, added refresh feedback and placed renewal guidance on the document that needs attention.

*Evidence:* [Registry and renewal tests](api/tests/test_web.py), [responsive browser checks](frontend/tests/web.spec.ts).

## 2026-11-25
*Hours:* ~3 hours
*Work*
- Audited all 13 stories and 53 acceptance criteria. Fixed reminders for licence-category deadlines, added the source to successful history rows and verified the official renewal link.
- Tested one-command startup with the default port occupied, documented the local workflow for contributors and made the header title return to Overview. Verified desktop keyboard and mobile navigation.

*Evidence:* [Acceptance audit](docs/acceptance.md), [local startup](README.md), [browser tests](frontend/tests/web.spec.ts).
