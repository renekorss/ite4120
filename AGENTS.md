# Agent instructions — TEHIK-aligned development

## Purpose and authority

This repository is developed in accordance with TEHIK's *Automaattestide kasutamise nõuded* and *Mittefunktsionaalsed nõuded* (MFN/NFR), version 2.4. Treat this file as the working checklist for every change.

The source documents remain authoritative. If a project decision conflicts with them, or a requirement is not feasible, record the non-compliance, its reason, impact, and proposed mitigation; do not silently waive it. Escalate exceptions for architectural approval.

- [Automated-testing requirements (PDF)](https://s3-web-1a.tehik.ee/tehik-live-web-prd/s3fs-public/2021-01/AV-72518077-280920-1256-30.pdf)
- [Non-functional requirements, v2.4 (PDF)](https://s3-web-1a.tehik.ee/tehik-live-web-prd/s3fs-public/2026-07/mittefunktsionaalsed-nouded.pdf)

## Before changing code or configuration

1. Read the relevant user story and acceptance criteria. Preserve the intended behaviour; do not invent product decisions.
2. Identify the affected requirements: security, personal-data handling, logging/auditing, accessibility and Estonian UI language, integrations, background jobs, persistence, performance, and tests.
3. Prefer a small, maintainable solution with explicit configuration and no hidden environment assumptions.
4. Do not commit credentials, tokens, real personal data, production exports, or hard-coded environment URLs. Use documented configuration and provide safe example values only.

## Requirement traceability and definition of done

- For every feature, bug fix, or material technical change, keep a traceable record that links: **user story or change request → applicable TEHIK/NFR requirement → implementation location → automated test or other verification evidence**. Put it in the pull request, issue, or a maintained requirements document.
- A change is not ready to hand off until all applicable items below are complete:
  - acceptance criteria and applicable NFRs have been reviewed;
  - Estonian user-facing copy, user-friendly error code, and accessible interaction have been added or confirmed unaffected;
  - security, personal-data, authorisation, logging, audit, and retention implications have been reviewed;
  - automated tests have been added/updated and the required checks pass;
  - configuration, API contract, migration, operational, and logging documentation have been updated where affected;
  - an exception, if any, is documented with owner, reason, mitigation, and required approval.
- The project must agree measurable unit-, integration-, and end-to-end-test coverage targets and how they are reported before its first release. Until then, do not reduce existing coverage and add tests for every changed behaviour and important failure path.

## Architecture and configuration

- Keep application services stateless and suitable for horizontal scaling; never depend on a particular server instance for a user session.
- Make environment-specific settings configurable at startup. In containerised deployments, use environment variables. Do not compile absolute URIs, secrets, email recipients, or environment details into the application.
- Use clear, descriptive configuration names. Document every required setting, safe default, owner, and whether a restart is required.
- Build integrations to fail gracefully: set timeouts, limit and reuse connections, isolate a dependency failure to the affected user flow, log it, show a useful user message, and recover without restarting once the dependency returns.
- Design public REST/SOAP interfaces for versioning. Treat external contracts as stable: validate inputs, retain compatibility unless a versioned change is agreed, and cover both successful and failure paths.
- Scheduled/background work must be observable and manually restartable by an authorised operator after failure. Make schedules and retry behaviour configurable and avoid duplicate deliveries.
- Store and log timestamps in UTC with timezone information; use ISO 8601 in text. Render dates/times in the user’s browser timezone.

## Web user interface

- This service has a web frontend only. Do not introduce a mobile-app implementation or mobile-specific assumptions.
- All user-facing UI text, notifications, validation, and error messages must be in Estonian unless a requirement explicitly adds another language. Structure strings so another language can be added through translation/configuration rather than code changes.
- Errors shown to users must be understandable, actionable, and include a manageable error code. Never expose stack traces, secrets, internal URLs, or personal data.
- Meet WCAG 2.1 AA unless the project agrees a different applicable standard. Provide accessible, semantic HTML; keyboard operation; visible focus; sensible form labels; and adequate contrast. Preserve submitted form data where feasible after a recoverable error.
- Verify accessibility with automated checks and manual keyboard testing for each material user-flow change. Include assistive-technology testing when the project’s release plan requires it.
- Use the Post/Redirect/Get pattern for actions that change state, so a page refresh cannot repeat a submission.
- Where sessions are used, warn users before expiry and make the warning interval configurable. Use secure session cookies only unless another cookie type is explicitly approved.
- Make external hand-offs explicit: notify the user before opening an external official service and give a useful fallback if it cannot be opened.

## Personal data, security, and X-Road

- Apply data minimisation: collect, return, display, and retain only what the feature needs. Never use production personal data in tests.
- Use encrypted transport for non-public data and authenticated/authorised channels where required. Keep security-sensitive behaviour and authorisation server-side.
- Enforce least privilege and separation of roles. Do not rely solely on hidden UI controls for authorisation.
- Use maintained dependencies and secure cryptographic primitives; do not implement cryptography yourself. Document any crypto or certificate use and make algorithm changes possible without pervasive code changes.
- Treat all external input as untrusted. Validate on the server, use parameterised data access, encode output appropriately, and protect state-changing requests against CSRF.
- Target OWASP ASVS Level 2 unless the project explicitly agrees otherwise. Address dependency and static-analysis findings; do not suppress a finding without a written rationale.
- For X-Road integrations, use the approved integration path. Do not write X-Road request payloads to application logs; log the X-Road identifier needed for correlation instead.
- Document each integration contract: owner, version, authentication, input/output validation, timeout, retry, idempotency, error mapping, and correlation-ID behaviour. Never pass an upstream technical error directly to the user.

## Data and persistence

- Version and automate database schema changes; include the migration with the change that needs it. Deployment scripts must be readable source, not compiled artefacts.
- Use purposeful field lengths and database-specific naming conventions. Document schemas, tables, and columns.
- Prefer logical deletion or otherwise preserve a reliable record of deletions. If the security classification requires historical versioning, preserve changes rather than overwriting records.
- Store files in object storage and retain references and metadata in the database, when file storage is needed.
- Create synthetic or anonymised test data that preserves meaningful types, lengths, and relationships but cannot identify real people.
- Document data retention: each data category, purpose, retention period, deletion/anonymisation method, and the roles permitted to access it and its audit records. Do not retain personal data merely because storage is available.

## Logging, audit, and observability

- Emit structured JSON logs: one event per line, with consistent Elastic Common Schema-style field names.
- Include a safe correlation/trace ID so related events can be linked. Do not use a reusable session ID as the correlation value.
- Log technical errors with time, error code, and diagnostic context appropriate to the configured log level. Make log level configurable.
- Maintain audit records for significant authentication, authorisation, and data access/change actions, including success and failure where required. Protect audit logs from alteration or deletion by the administrators whose actions they record.
- Keep direct personal data, secrets, credentials, session cookies/tokens, and full sensitive request bodies out of routine system logs. Represent missing values explicitly and encode control characters.
- Update logging documentation and examples when a functional change adds, removes, or changes an auditable event.

## Code quality and documentation

- Write source-code comments and generated API documentation in English. Document public functions and interfaces clearly enough for another developer to maintain them.
- Follow the relevant Google style guide unless this repository establishes a stricter formatter/linter. Use the project formatter and do not add unused code; unfinished code must be behind an intentional feature flag.
- Use Conventional Commits for commit messages, for example `feat: add reminder preference validation` or `fix: handle X-Road timeout`.
- Keep operational documentation current: local setup, configuration, build/package creation, deployment, test execution, log locations, rollback/recovery steps, and any manual background-job operation.
- When adding a dependency, record its purpose and ensure it is included in the project’s SBOM-generation approach. Deliverables need reproducible build/package instructions and SHA-256 checksums when the version-control platform does not provide them.
- Commit the package-manager lockfile. Run vulnerability scanning as part of delivery checks. Do not introduce an unmaintained dependency, a dependency with an unacceptable known vulnerability, or a licence incompatibility without a documented and approved exception.

## Testing and delivery gates

- Add or update automated tests with every behaviour change. Tests belong with the code unless they are explicitly managed in their own test repository.
- Unit and integration tests are mandatory build gates: run them before creating a build. Unit tests test the project’s code, not third-party libraries.
- Integration tests must exercise component collaboration, using controlled test data, mocks, or containers where appropriate.
- Interface tests run after deployment against the real connected systems—not mocks—and cover both positive and negative flows. For X-Road flows, use the agreed X-Road test capability.
- End-to-end tests must cover relevant functional and non-functional acceptance criteria for the web frontend and backend.
- Assess and automate, where applicable, resilience and load tests. Run load tests at least at sprint end to detect regressions; failed post-deploy test gates require rollback outside development environments.
- Ensure tests can run unattended in a GitLab Pipeline and Docker container. The intended pipeline order is: **unit + integration tests → build → deploy → interface tests → end-to-end tests → resilience tests → load tests**.
- Before handoff, run the project’s available formatter, lint/static analysis, unit/integration tests, and build. Report exactly what was run and any checks that could not run.
- When the implementation stack is selected, maintain the exact canonical commands for format, lint, unit tests, integration tests, end-to-end tests, build, accessibility checks, dependency/security scan, SBOM generation, and local run in `README.md` or a dedicated contributor guide. Agents must use those commands rather than guessing alternatives.

## Prohibited shortcuts

Do not:

- bypass, weaken, or delete a test merely to make a pipeline pass;
- disable security controls, security headers, audit logging, or validation without an approved, documented exception;
- log secrets, session material, direct personal data, or complete sensitive request/response bodies;
- commit credentials, use production personal data in non-production environments, or modify production data directly outside an approved operational procedure;
- expose an upstream integration's technical details to users;
- add an unsupported, unmaintained, or unapproved dependency; or
- claim that a check passed when it was not run.

## Change handoff

In the final change summary, state:

1. What changed and the user story or requirement it supports.
2. Tests and quality checks run, with their outcome.
3. Any configuration, migration, deployment, logging, or documentation changes required.
4. Any NFR exception, security trade-off, unresolved risk, or approval needed.
