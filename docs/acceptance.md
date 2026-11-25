# Driving Licence Reminder acceptance audit

Scope: English browser demo, seven synthetic accounts, mock licence and medical
registries, PostgreSQL and scheduled Web Push. Numbers below follow the bullet
order in [user-stories.md](../user-stories.md). The parent story spans US-04,
05, 06 and 08–12, from reading a deadline to opening guidance from a reminder.

| Story | Criterion-by-criterion result in the local demo | Implementation and verification |
| --- | --- | --- |
| US-01 | AC1. An enabled demo code opens the profile. AC2. An unknown code shows an actionable error. AC3. The session grants access to the driver’s own information and settings. | login.tsx, main.py. Browser keyboard login, all sign-in choices, API demo login and cross-user access tests. |
| US-02 | AC1. Logout revokes the session. AC2. Protected API reads require fresh authentication and the browser returns to sign-in. | main.tsx, main.py. Browser logout, API logout revocation and protected-read tests. |
| US-03 | AC1. Overview shows current status. AC2. Assessed states are Valid, At risk and Invalid. AC3. Affected drivers see the reason or document requiring action. An account awaiting its first successful lookup shows Unknown. | Overview, driving_data. The signed-in header title links to Overview. Browser tests cover desktop keyboard activation and a mobile click (WCAG keyboard access). API status variations, no-data and medical regression tests, mobile medical browser flow. |
| US-04 | AC1. Licence shows categories and available dates. AC2. Applicable medical records show status and expiry. AC3. The earliest known relevant deadline appears on Overview. A source entitlement date is explicitly labelled. Missing document dates remain unavailable. | LicencePage, driving_data. API source normalization, combined registry, category-deadline and card-action tests. |
| US-05 | AC1. Refresh queries both mock registries. Approved external interface acceptance is open. AC2. Success updates status and details. AC3. Failure shows a safe error and retains the last good snapshot and timestamp. AC4. The last successful update is visible. | store.py, upstream.py, main.tsx. Combined-registry, failure-recovery, unavailable and slow-refresh tests. |
| US-06 | AC1. A relevant card opens Estonia-specific guidance. AC2. Guidance distinguishes licence, certificate and combined action. AC3. Each gives a practical next step. AC4. Each offers the official e-service. | renewal.tsx, locales/en.json, guidance endpoint. Four API card/guidance scenarios and desktop/mobile renewal tests. |
| US-07 | AC1. Continue opens the configured official URL in a new browser tab. AC2. A dialog identifies the external service first. AC3. The configured default is the official English driver page listing driving licence exchange. AC4. A blocked popup or user-reported opening failure exposes the address and error code. | renewal.tsx, OFFICIAL_RENEWAL_URL. Browser hand-off and blocked-popup checks. The destination after official sign-in is outside the demo. See the [official driver e-service](https://eteenindus.mnt.ee/juht.jsf?lang=en). |
| US-08 | AC1. Enable registers this browser and saves the intervals for eligible deadlines. AC2. The switch shows On and the save is confirmed. AC3. Browser permission precedes registration. AC4. Denial explains how to recover and preserves settings. | reminders.tsx, push.ts, delivery.py. Permission-denied browser test, subscription API tests and recorded Chrome delivery exercise in the web guide. |
| US-09 | AC1. Saved intervals are loaded. AC2. Checkboxes allow 90, 30 and 7 days. AC3. Saving persists the selection and cancels removed intervals. AC4. The page confirms the save. | reminders.tsx, preferences endpoint. Small-screen browser save and readback, API interval-change cancellation and relogin tests. |
| US-10 | AC1. Sent notices sort newest first. AC2. Each shows local send date and time. AC3. Each identifies the document. AC4. Its expiry is displayed. AC5. The default API limit is 20. | history.tsx, notifications endpoint. Recent notification history test with 21 sent notices, sent-only delivery and category reminder tests, history field rendering. |
| US-11 | AC1. Turning off opens confirmation. AC2. Confirming disables delivery and cancels unsent work. AC3. The off state offers enable again. | reminders.tsx, main.py, delivery.py. Mobile confirmation/cancellation, API disable and worker eligibility tests. |
| US-12 | AC1. The worker automatically checks eligible licence, category and required certificate deadlines. AC2. Selected 90/30/7-day intervals use UTC calendar dates. AC3. The notification names the document and date. AC4. It recommends opening renewal instructions and clicking opens that route. AC5. Eligibility is rechecked against current dates and preferences before sending. | delivery.py, sw.js, migration 006. Category tests for all three intervals, medical target, obsolete deadline, duplicate worker, permission and closed-tab push checks. |
| US-13 | AC1. Checks sort newest first. AC2. Rows show local date/time. AC3. Each has an outcome label. AC4. Successful rows distinguish first result, changed and unchanged. AC5. Each successful row shows its registry source. AC6. Failed rows show a safe reason. AC7. The last successful data survives failure. AC8. The latest success is marked. AC9. The default list is five. | history.tsx, check_view, checks endpoint. API first/repeat/failure/latest-success and limit tests, browser status history and source assertion. |

## Acceptance boundaries

- US-05 requires an approved X-Road integration. The local adapter deliberately accepts only marked mock responses. The integration owner must provide approved test access and verify positive and negative cases on that connection before sign-off. The mock provides an entitlement end date and a separate synthetic medical record. Confirm real document expiry and medical provenance with that owner for US-04.
- US-01 uses the requested public demo accounts with server-side session isolation. Identity assurance for real drivers needs an approved authentication integration.
- US-08/12 have a previously recorded provider-backed Chrome delivery, with a repeatable procedure in [the web guide](web.md#scheduled-browser-notifications). The automated browser test injects a push event. Firefox/Safari provider-backed delivery remains unverified.
- Accessibility evidence includes keyboard navigation and automated WCAG 2.1 AA scans of exercised screens. The project’s release-wide NFR, interface and load gates remain separate from these functional checks.

## Local verification on 25 November 2026

The one-command launcher ran against the existing demo volume on port 5174
while port 5173 was occupied. Chrome passed all eight browser scenarios against
that instance, including the real popup with an intercepted destination, blocked
popup fallback, saved reminder intervals, per-check source, keyboard navigation
and axe checks. The frontend passed two unit tests, Prettier, TypeScript and
the production build. The disposable API/worker suite passed 90 tests with 96%
statement coverage and one TestClient deprecation warning. Ruff, 16 mock tests,
six repository checks and the database migration/rollback/reapplication suite
passed. No live X-Road interface or new provider-backed delivery was exercised
during this audit.
