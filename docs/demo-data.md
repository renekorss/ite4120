# Synthetic driving data

Load the fixtures into the running local database after applying migrations:

```sh
./scripts/seed-demo.sh
```

Refresh the table list/data in TablePlus. Start with `user_account` and
`latest_successful_check`; join `driving_licence` and `medical_certificate` using
`check_id`, and `licence_category` using `licence_id`.

| Synthetic account (`identity_subject`) | Current scenario |
| --- | --- |
| `demo-valid` | Valid licence and certificate; reminders disabled |
| `demo-licence-90-days` | Licence expires in 90 days; categories B and BE |
| `demo-medical-30-days` | Certificate expires in 30 days; latest refresh failed, previous success retained; selected intervals 30 and 7 |
| `demo-both-7-days` | Both expire in 7 days; separate licence/certificate reminder targets |
| `demo-licence-expired` | Licence expired 10 days ago; earlier successful snapshot and sent reminder |
| `demo-medical-expired` | Certificate expired 5 days ago despite a valid licence; reminders disabled |
| `demo-renewed` | New licence expiry and changed driving status; old pending reminder cancelled, sent history preserved |

Dates are relative to the **first load's UTC date**, then remain unchanged. Refreshing
these examples over time requires a fresh disposable database, not rerunning the seed:
the seed is transactional and skips loading when its dataset marker exists. It never
truncates tables or overwrites existing records. Reserved fixture UUID prefixes are
`f1000000` through `f8000000`. A conflicting unrelated UUID rolls back the load rather
than overwriting data. A partial manually edited fixture set is not automatically repaired.

The dataset has 7 accounts, 10 checks, 9 licence snapshots, 12 category memberships,
9 certificate snapshots, 7 preferences, 20 selected intervals, 7 notifications,
2 delivery attempts and 7 `mock.seeded` audit events. Notifications use `in_app`;
no browser endpoint, authentication session or usable secret is created. Sent states
are simulated records, not evidence of any real delivery. It is not a mock login provider.

## X-Road boundary

These are minimized **normalized database examples**, not genuine X-Road responses or
an implementation of an undocumented API. All identities use the issuer
`synthetic-driving-reminder-v1`; every request ID starts with `MOCK-NOT-XROAD-`.
The schema's fixed `source_code` describes the integration being simulated, not proof
that these records came from the Transport Administration. Keep these accounts out
of any real integration/delivery path; remove them by using a fresh environment before
connecting to real services. Fixtures are separate from Liquibase and never loaded by
normal migrations, startup or production deployment.

The [official X-Road Playground](https://x-road.global/xroad-playground) provides SOAP
random-number/greeting services and REST business-data/statistics services. It does not
list a driving-licence or medical-certificate service. Its server UI access is read-only.
Use it separately to learn X-Road headers, addressing and service invocation; it cannot
validate the future Transport Administration payload mapping.

Domain examples distinguish licence validity from medical-certificate validity, as
covered in [Transport Administration guidance](https://www.transpordiamet.ee/tervisetoend-autojuhile).
Fixture issue/expiry dates and at-risk classifications are illustrative, not legal
rules. Actual source field names, category scope, validity rules, medical applicability,
status/risk mappings and correlation IDs require the approved X-Road contracts already
listed in `docs/database.md`.

## Verification and traceability

Request: create realistic synthetic driving data. Supports US-03–US-06 and US-08–US-13;
no new product behavior is implemented. TEHIK NFR 5.2 and `AGENTS.md` require synthetic
non-production data and persistence integrity. Implementation is
`database/fixtures/demo.sql`; execution is `scripts/seed-demo.sh`.

`./scripts/test-database.sh` tests the fixture load and repeat load in its disposable
Docker project, alongside migration and database constraint checks. Assertions in
`database/tests/demo.sql` cover counts, current status, failed-refresh fallback,
renewal/cancellation, historical timestamps, mock provenance and absence of session or
push secrets. No new dependency, schema migration, source payload logging or production
configuration is introduced. The seed records one safe `mock.seeded` audit event per
synthetic account; it does not implement runtime audit emission.

For mocked upstream HTTP requests using the published test-service JSON contract,
use the separate [X-Road HTTP mock](xroad-mock.md). This SQL dataset is only for
browsing local persistence and is not the response body of an X-Road service.
