\set ON_ERROR_STOP on
BEGIN;
SET LOCAL TIME ZONE 'UTC';
-- Explicit opt-in development fixtures, never included in Liquibase changesets.
-- Serialise seed invocations and skip the entire dataset once its marker exists.
LOCK TABLE user_account IN SHARE ROW EXCLUSIVE MODE;
SELECT EXISTS (
    SELECT 1 FROM user_account WHERE identity_issuer = 'synthetic-driving-reminder-v1'
) AS demo_exists \gset
\if :demo_exists
\echo 'Synthetic demo accounts already exist; existing data was left unchanged.'
\else
CREATE TEMP TABLE demo_scenario (
    scenario smallint PRIMARY KEY,
    subject varchar(40) NOT NULL,
    status varchar(12) NOT NULL,
    reason varchar(64),
    licence_days integer NOT NULL,
    medical_days integer NOT NULL,
    enabled boolean NOT NULL
) ON COMMIT DROP;
INSERT INTO demo_scenario VALUES
    (1, 'demo-valid', 'valid', NULL, 730, 365, false),
    (2, 'demo-licence-90-days', 'at_risk', 'LICENCE_EXPIRY_APPROACHING', 90, 365, true),
    (3, 'demo-medical-30-days', 'at_risk', 'MEDICAL_EXPIRY_APPROACHING', 365, 30, true),
    (4, 'demo-both-7-days', 'at_risk', 'BOTH_EXPIRY_APPROACHING', 7, 7, true),
    (5, 'demo-licence-expired', 'invalid', 'LICENCE_EXPIRED', -10, 365, true),
    (6, 'demo-medical-expired', 'invalid', 'MEDICAL_EXPIRED', 365, -5, false),
    (7, 'demo-renewed', 'valid', NULL, 3650, 365, true);

-- Reserved fixture UUID prefixes: f100 accounts, f200 checks, f300 licences,
-- f400 certificates, f500 notifications, f600 attempts, f700 audit, f800 traces.
INSERT INTO user_account(id, identity_issuer, identity_subject, created_at)
SELECT ('f1000000-0000-4000-8000-' || lpad(scenario::text, 12, '0'))::uuid,
    'synthetic-driving-reminder-v1', subject, CURRENT_TIMESTAMP - interval '1 year'
FROM demo_scenario;

-- Previous successful snapshot for the renewal scenario only.
INSERT INTO status_check(id, user_id, requested_at, completed_at, outcome, trace_id,
    xroad_request_id, driving_status, reason_code, medical_requirement, status_changed)
VALUES ('f2000000-0000-4000-8000-000000000107', 'f1000000-0000-4000-8000-000000000007',
    CURRENT_TIMESTAMP - interval '90 days' - interval '2 seconds', CURRENT_TIMESTAMP - interval '90 days',
    'successful', 'f8000000-0000-4000-8000-000000000107', 'MOCK-NOT-XROAD-RENEWAL-BEFORE',
    'at_risk', 'LICENCE_EXPIRY_APPROACHING', 'required', NULL);
INSERT INTO driving_licence(id, check_id, document_status, issued_on, expires_on)
VALUES ('f3000000-0000-4000-8000-000000000107', 'f2000000-0000-4000-8000-000000000107',
    'valid', CURRENT_DATE - 3640, CURRENT_DATE + 10);
INSERT INTO licence_category VALUES ('f3000000-0000-4000-8000-000000000107', 'B');
INSERT INTO medical_certificate(id, check_id, certificate_status, issued_on, expires_on)
VALUES ('f4000000-0000-4000-8000-000000000107', 'f2000000-0000-4000-8000-000000000107',
    'valid', CURRENT_DATE - 1460, CURRENT_DATE + 365);

-- Historical snapshot supporting the reminder sent before licence expiry.
INSERT INTO status_check(id, user_id, requested_at, completed_at, outcome, trace_id,
    xroad_request_id, driving_status, reason_code, medical_requirement, status_changed)
VALUES ('f2000000-0000-4000-8000-000000000105', 'f1000000-0000-4000-8000-000000000005',
    CURRENT_TIMESTAMP - interval '41 days' - interval '2 seconds', CURRENT_TIMESTAMP - interval '41 days',
    'successful', 'f8000000-0000-4000-8000-000000000105', 'MOCK-NOT-XROAD-BEFORE-EXPIRY',
    'at_risk', 'LICENCE_EXPIRY_APPROACHING', 'required', NULL);
INSERT INTO driving_licence(id, check_id, document_status, issued_on, expires_on)
VALUES ('f3000000-0000-4000-8000-000000000105', 'f2000000-0000-4000-8000-000000000105',
    'valid', (CURRENT_DATE - 10 - interval '10 years')::date, CURRENT_DATE - 10);
INSERT INTO licence_category VALUES ('f3000000-0000-4000-8000-000000000105', 'B');
INSERT INTO medical_certificate(id, check_id, certificate_status, issued_on, expires_on)
VALUES ('f4000000-0000-4000-8000-000000000105', 'f2000000-0000-4000-8000-000000000105',
    'valid', CURRENT_DATE - 1460, CURRENT_DATE + 365);

INSERT INTO status_check(id, user_id, requested_at, completed_at, outcome, trace_id,
    xroad_request_id, driving_status, reason_code, medical_requirement, status_changed)
SELECT ('f2000000-0000-4000-8000-' || lpad(scenario::text, 12, '0'))::uuid,
    ('f1000000-0000-4000-8000-' || lpad(scenario::text, 12, '0'))::uuid,
    CURRENT_TIMESTAMP - interval '1 hour' - interval '2 seconds', CURRENT_TIMESTAMP - interval '1 hour',
    'successful', ('f8000000-0000-4000-8000-' || lpad(scenario::text, 12, '0'))::uuid,
    'MOCK-NOT-XROAD-' || subject, status, reason, 'required',
    CASE WHEN scenario IN (5, 7) THEN true ELSE NULL END
FROM demo_scenario;

INSERT INTO driving_licence(id, check_id, document_status, issued_on, expires_on)
SELECT ('f3000000-0000-4000-8000-' || lpad(scenario::text, 12, '0'))::uuid,
    ('f2000000-0000-4000-8000-' || lpad(scenario::text, 12, '0'))::uuid,
    CASE WHEN licence_days < 0 THEN 'expired' ELSE 'valid' END,
    (CURRENT_DATE + licence_days - interval '10 years')::date, CURRENT_DATE + licence_days
FROM demo_scenario;
INSERT INTO licence_category
SELECT ('f3000000-0000-4000-8000-' || lpad(scenario::text, 12, '0'))::uuid, 'B'
FROM demo_scenario;
INSERT INTO licence_category VALUES
    ('f3000000-0000-4000-8000-000000000001', 'A'),
    ('f3000000-0000-4000-8000-000000000002', 'BE'),
    ('f3000000-0000-4000-8000-000000000004', 'AM');
INSERT INTO medical_certificate(id, check_id, certificate_status, issued_on, expires_on)
SELECT ('f4000000-0000-4000-8000-' || lpad(scenario::text, 12, '0'))::uuid,
    ('f2000000-0000-4000-8000-' || lpad(scenario::text, 12, '0'))::uuid,
    CASE WHEN medical_days < 0 THEN 'expired' ELSE 'valid' END,
    (CURRENT_DATE + medical_days - interval '5 years')::date, CURRENT_DATE + medical_days
FROM demo_scenario;

-- Latest refresh failed for scenario 3; its successful snapshot remains current.
INSERT INTO status_check(id, user_id, requested_at, completed_at, outcome, trace_id, xroad_request_id, error_code)
VALUES ('f2000000-0000-4000-8000-000000000203', 'f1000000-0000-4000-8000-000000000003',
    CURRENT_TIMESTAMP - interval '10 minutes' - interval '15 seconds', CURRENT_TIMESTAMP - interval '10 minutes',
    'failed', 'f8000000-0000-4000-8000-000000000203', 'MOCK-NOT-XROAD-TIMEOUT', 'XR_TIMEOUT');

INSERT INTO reminder_preference(user_id, enabled, updated_at)
SELECT ('f1000000-0000-4000-8000-' || lpad(scenario::text, 12, '0'))::uuid,
    enabled, CURRENT_TIMESTAMP - interval '32 days'
FROM demo_scenario;
INSERT INTO reminder_interval(user_id, days_before)
SELECT p.user_id, days_before FROM reminder_preference p
JOIN user_account u ON u.id = p.user_id
CROSS JOIN (VALUES (90), (30), (7)) AS supported(days_before)
WHERE u.identity_issuer = 'synthetic-driving-reminder-v1';
-- One user has deliberately customized their selected intervals.
DELETE FROM reminder_interval WHERE user_id = 'f1000000-0000-4000-8000-000000000003' AND days_before = 90;

-- Pending reminders for upcoming next deadlines. All use in-app delivery:
-- no usable browser endpoint, encrypted-looking fake secret or login is seeded.
INSERT INTO notification(id, user_id, check_id, document_kind, licence_id, medical_certificate_id,
    expires_on, days_before, scheduled_at, channel, state, created_at)
SELECT ('f5000000-0000-4000-8000-' || lpad((s.scenario * 10 + target.target_number)::text, 12, '0'))::uuid,
    c.user_id, c.id, target.kind,
    CASE WHEN target.kind = 'driving_licence' THEN l.id END,
    CASE WHEN target.kind = 'medical_certificate' THEN m.id END,
    CASE WHEN target.kind = 'driving_licence' THEN l.expires_on ELSE m.expires_on END,
    CASE s.scenario WHEN 2 THEN 90 WHEN 3 THEN 30 ELSE 7 END,
    CURRENT_TIMESTAMP + interval '1 hour', 'in_app', 'pending', CURRENT_TIMESTAMP - interval '30 minutes'
FROM demo_scenario s
JOIN status_check c ON c.id = ('f2000000-0000-4000-8000-' || lpad(s.scenario::text, 12, '0'))::uuid
JOIN driving_licence l ON l.check_id = c.id
JOIN medical_certificate m ON m.check_id = c.id
CROSS JOIN (VALUES (1, 'driving_licence'), (2, 'medical_certificate')) AS target(target_number, kind)
WHERE (s.scenario = 2 AND target.kind = 'driving_licence')
    OR (s.scenario = 3 AND target.kind = 'medical_certificate') OR s.scenario = 4;

-- Historical sent 30-day reminder for a now-expired licence (sent 40 days ago).
INSERT INTO notification(id, user_id, check_id, document_kind, licence_id, expires_on,
    days_before, scheduled_at, channel, state, created_at, sent_at)
SELECT 'f5000000-0000-4000-8000-000000000051', c.user_id, c.id, 'driving_licence', l.id, l.expires_on,
    30, (l.expires_on - 30)::timestamptz + interval '9 hours', 'in_app', 'sent',
    CURRENT_TIMESTAMP - interval '41 days', (l.expires_on - 30)::timestamptz + interval '9 hours 1 minute'
FROM status_check c JOIN driving_licence l ON l.check_id = c.id
WHERE c.id = 'f2000000-0000-4000-8000-000000000105';

-- Cancelled reminder for the previous document after renewal, plus a sent reminder.
INSERT INTO notification(id, user_id, check_id, document_kind, licence_id, expires_on,
    days_before, scheduled_at, channel, state, created_at, sent_at)
SELECT ('f5000000-0000-4000-8000-' || lpad((700 + lead.days)::text, 12, '0'))::uuid,
    c.user_id, c.id, 'driving_licence', l.id, l.expires_on, lead.days,
    (l.expires_on - lead.days)::timestamptz + interval '9 hours', 'in_app',
    CASE WHEN lead.days = 30 THEN 'cancelled' ELSE 'sent' END,
    CURRENT_TIMESTAMP - interval '90 days',
    CASE WHEN lead.days = 90 THEN (l.expires_on - 90)::timestamptz + interval '9 hours 1 minute' END
FROM status_check c JOIN driving_licence l ON l.check_id = c.id
CROSS JOIN (VALUES (90), (30)) AS lead(days)
WHERE c.id = 'f2000000-0000-4000-8000-000000000107';

INSERT INTO notification_attempt(id, notification_id, attempt_number, started_at, completed_at,
    outcome, error_code, trace_id)
SELECT ('f6000000-0000-4000-8000-' || right(n.id::text, 12))::uuid, n.id, 1,
    n.sent_at - interval '1 second', n.sent_at, 'successful', NULL,
    ('f8000000-0000-4000-8000-' || lpad((1000 + row_number() OVER (ORDER BY n.id))::text, 12, '0'))::uuid
FROM notification n JOIN user_account u ON u.id = n.user_id
WHERE u.identity_issuer = 'synthetic-driving-reminder-v1' AND n.state = 'sent';

INSERT INTO audit_event(id, subject_user_id, actor_kind, action_code, outcome, trace_id)
SELECT ('f7000000-0000-4000-8000-' || lpad(scenario::text, 12, '0'))::uuid,
    ('f1000000-0000-4000-8000-' || lpad(scenario::text, 12, '0'))::uuid,
    'system', 'mock.seeded', 'success',
    ('f8000000-0000-4000-8000-' || lpad((2000 + scenario)::text, 12, '0'))::uuid
FROM demo_scenario;
\echo 'Loaded seven synthetic driving scenarios; no X-Road call or notification delivery occurred.'
\endif
COMMIT;
