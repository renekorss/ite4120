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
*Corrections:*
- Removed the trailing newline when copying the database password for TablePlus
- Added the missing diary entries for the database homework
- Isolated test database ports from the local TablePlus connection before creating the pull request
*Evidence:*
- Setup instructions: `README.md`
- Operations and test commands: `docs/database-operations.md`
- Local database port mapping: `compose.yaml`
- TablePlus connection confirmed working
