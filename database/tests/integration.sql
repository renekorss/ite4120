\set ON_ERROR_STOP on
BEGIN;
SET TIME ZONE 'UTC';
CREATE FUNCTION pg_temp.assert_true(value boolean, label text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    IF value IS DISTINCT FROM true THEN RAISE EXCEPTION 'Assertion failed: %', label; END IF;
END $$;
CREATE FUNCTION pg_temp.reject(statement text, expected_state text) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE actual_state text;
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS actual_state = RETURNED_SQLSTATE;
        IF actual_state = expected_state THEN RETURN; END IF;
        RAISE EXCEPTION 'Expected SQLSTATE %, got %', expected_state, actual_state;
    END;
    RAISE EXCEPTION 'Statement unexpectedly accepted: %', statement;
END $$;

-- Fabricated opaque IDs, never real people or registry responses.
INSERT INTO user_account(id, identity_issuer, identity_subject) VALUES
('00000000-0000-4000-8000-000000000001', 'test-issuer', 'synthetic-one'),
('00000000-0000-4000-8000-000000000002', 'test-issuer', 'synthetic-two');
SELECT pg_temp.reject($q$INSERT INTO user_account VALUES
('00000000-0000-4000-8000-000000000003', 'test-issuer', 'synthetic-one', now(), NULL)$q$, '23505');
INSERT INTO web_session(id, user_id, token_hash, expires_at) VALUES
('00000000-0000-4000-8000-000000000010', '00000000-0000-4000-8000-000000000001', decode(repeat('01', 32), 'hex'), now() + interval '1 hour');
SELECT pg_temp.reject($q$UPDATE web_session SET expires_at = created_at$q$, '23514');
SELECT pg_temp.reject($q$UPDATE web_session SET token_hash = decode('01', 'hex')$q$, '23514');
UPDATE web_session SET revoked_at = now();
SELECT pg_temp.assert_true((SELECT revoked_at IS NOT NULL FROM web_session), 'logout revocation persisted');

INSERT INTO status_check(id, user_id, requested_at, completed_at, outcome, trace_id,
    driving_status, medical_requirement, status_changed) VALUES
('00000000-0000-4000-8000-000000000020', '00000000-0000-4000-8000-000000000001',
    '2026-10-01T10:00:00Z', '2026-10-01T10:00:01Z', 'successful',
    '00000000-0000-4000-8000-000000000090', 'valid', 'required', NULL);
INSERT INTO status_check(id, user_id, requested_at, completed_at, outcome, trace_id, error_code) VALUES
('00000000-0000-4000-8000-000000000021', '00000000-0000-4000-8000-000000000001',
    '2026-10-02T10:00:00Z', '2026-10-02T10:00:01Z', 'failed',
    '00000000-0000-4000-8000-000000000091', 'XR_TIMEOUT');
SELECT pg_temp.assert_true((SELECT id = '00000000-0000-4000-8000-000000000020' FROM latest_successful_check),
    'failure retains last successful snapshot');
SELECT pg_temp.reject($q$UPDATE status_check SET error_code = NULL WHERE outcome = 'failed'$q$, '23514');
SELECT pg_temp.reject($q$UPDATE status_check SET driving_status = 'invalid' WHERE outcome = 'successful'$q$, '23514');
-- A later complete success becomes current and can record a changed assessment.
INSERT INTO status_check(id, user_id, requested_at, completed_at, outcome, trace_id,
    driving_status, reason_code, medical_requirement, status_changed) VALUES
('00000000-0000-4000-8000-000000000022', '00000000-0000-4000-8000-000000000001',
    '2026-10-03T10:00:00Z', '2026-10-03T10:00:01Z', 'successful',
    '00000000-0000-4000-8000-000000000094', 'at_risk', 'EXPIRY_APPROACHING', 'unknown', true);
SELECT pg_temp.assert_true((SELECT id = '00000000-0000-4000-8000-000000000022'
    AND status_changed AND driving_status = 'at_risk' FROM latest_successful_check), 'new success replaces current assessment');
DELETE FROM status_check WHERE id = '00000000-0000-4000-8000-000000000022';
INSERT INTO driving_licence(id, check_id, document_status, issued_on, expires_on) VALUES
('00000000-0000-4000-8000-000000000030', '00000000-0000-4000-8000-000000000020', 'valid', '2020-01-01', '2027-01-01');
SELECT pg_temp.reject($q$INSERT INTO driving_licence(id, check_id, document_status) VALUES
('00000000-0000-4000-8000-000000000031', '00000000-0000-4000-8000-000000000021', 'unknown')$q$, '23503');
INSERT INTO licence_category VALUES ('00000000-0000-4000-8000-000000000030', 'B');
SELECT pg_temp.reject($q$INSERT INTO licence_category VALUES
('00000000-0000-4000-8000-000000000030', 'B')$q$, '23505');
SELECT pg_temp.reject($q$UPDATE driving_licence SET expires_on = '2019-01-01'$q$, '23514');
INSERT INTO medical_certificate(id, check_id, certificate_status, expires_on) VALUES
('00000000-0000-4000-8000-000000000040', '00000000-0000-4000-8000-000000000020', 'valid', '2026-12-01');
SELECT pg_temp.assert_true((SELECT min(expires_on) = date '2026-12-01' FROM (
    SELECT expires_on FROM driving_licence UNION ALL SELECT expires_on FROM medical_certificate) deadlines), 'earliest of all known deadlines');
INSERT INTO reminder_preference(user_id) VALUES ('00000000-0000-4000-8000-000000000001');
INSERT INTO reminder_interval SELECT '00000000-0000-4000-8000-000000000001', days FROM (VALUES (90), (30), (7)) AS intervals(days);
SELECT pg_temp.assert_true((SELECT NOT enabled FROM reminder_preference), 'opt-in disabled by default');
SELECT pg_temp.reject($q$UPDATE reminder_interval SET days_before = 14$q$, '23514');
SELECT pg_temp.reject($q$INSERT INTO reminder_interval VALUES ('00000000-0000-4000-8000-000000000002', 7)$q$, '23503');
UPDATE reminder_preference SET enabled = true, updated_at = now();
INSERT INTO notification(id, user_id, check_id, document_kind, licence_id, expires_on, days_before, scheduled_at, channel)
VALUES ('00000000-0000-4000-8000-000000000050', '00000000-0000-4000-8000-000000000001',
'00000000-0000-4000-8000-000000000020', 'driving_licence', '00000000-0000-4000-8000-000000000030', '2027-01-01', 90, '2026-10-03T07:00:00Z', 'in_app');
SELECT pg_temp.reject($q$UPDATE notification SET user_id = '00000000-0000-4000-8000-000000000002'$q$, '23503');
SELECT pg_temp.reject($q$UPDATE notification SET expires_on = '2027-02-01'$q$, '23503');
SELECT pg_temp.reject($q$UPDATE notification SET channel = 'web_push'$q$, '23514');
SELECT pg_temp.reject($q$UPDATE notification SET state = 'sent'$q$, '23514');
SELECT pg_temp.reject($q$INSERT INTO notification SELECT
'00000000-0000-4000-8000-000000000051', user_id, check_id, document_kind, licence_id,
medical_certificate_id, expires_on, days_before, scheduled_at, channel, subscription_id,
state, claimed_until, sent_at, error_code, created_at FROM notification$q$, '23505');
INSERT INTO web_push_subscription(id, user_id, encrypted_subscription, encryption_key_ref) VALUES
('00000000-0000-4000-8000-000000000060', '00000000-0000-4000-8000-000000000002', decode('0102', 'hex'), 'test-key');
SELECT pg_temp.reject($q$UPDATE notification SET channel = 'web_push', subscription_id = '00000000-0000-4000-8000-000000000060'$q$, '23503');
INSERT INTO notification_attempt(id, notification_id, attempt_number, outcome, trace_id)
VALUES ('00000000-0000-4000-8000-000000000070', '00000000-0000-4000-8000-000000000050', 1, 'pending', '00000000-0000-4000-8000-000000000092');
SELECT pg_temp.reject($q$UPDATE notification_attempt SET outcome = 'failed', completed_at = now()$q$, '23514');
UPDATE notification_attempt SET outcome = 'failed', completed_at = now(), error_code = 'DELIVERY_UNAVAILABLE';
UPDATE notification SET state = 'cancelled';
UPDATE reminder_preference SET enabled = false, updated_at = now();
SELECT pg_temp.assert_true((SELECT state = 'cancelled' FROM notification), 'cancellation persisted');
UPDATE notification SET state = 'sent', sent_at = now();
SELECT pg_temp.assert_true((SELECT count(*) = 1 FROM notification WHERE sent_at IS NOT NULL), 'sent history retained');
SELECT pg_temp.reject($q$DELETE FROM status_check WHERE outcome = 'successful'$q$, '23503');

SET ROLE reminder_runtime;
INSERT INTO audit_event(id, actor_user_id, subject_user_id, actor_kind, action_code, outcome, trace_id)
VALUES ('00000000-0000-4000-8000-000000000080', '00000000-0000-4000-8000-000000000001',
'00000000-0000-4000-8000-000000000001', 'user', 'reminders.disabled', 'success', '00000000-0000-4000-8000-000000000093');
SELECT pg_temp.reject('SELECT * FROM audit_event', '42501');
SELECT pg_temp.reject($q$UPDATE audit_event SET action_code = 'tampered'$q$, '42501');
SELECT pg_temp.reject('DELETE FROM audit_event', '42501');
SELECT pg_temp.reject('TRUNCATE audit_event', '42501');
SELECT pg_temp.reject('CREATE TABLE forbidden(id integer)', '42501');
SELECT pg_temp.reject('SELECT * FROM databasechangelog', '42501');
SELECT pg_temp.reject('DELETE FROM driving_licence', '42501');
RESET ROLE;
SET ROLE reminder_auditor;
SELECT pg_temp.assert_true((SELECT count(*) = 1 FROM audit_event), 'auditor can read');
SELECT pg_temp.reject('DELETE FROM audit_event', '42501');
SELECT pg_temp.reject('SELECT * FROM medical_certificate', '42501');
RESET ROLE;
SET ROLE reminder_retention;
SELECT pg_temp.reject('DELETE FROM audit_event', '42501');
RESET ROLE;
SELECT pg_temp.reject($q$DELETE FROM user_account WHERE id = '00000000-0000-4000-8000-000000000001'$q$, '23503');
-- Independent audit custodian anonymizes expired account links, preserving event.
UPDATE audit_event SET actor_user_id = NULL, subject_user_id = NULL, actor_kind = 'anonymous';
DELETE FROM user_account WHERE id = '00000000-0000-4000-8000-000000000001';
SELECT pg_temp.assert_true((SELECT count(*) = 0 FROM notification), 'account purge cascades outbox');
SELECT pg_temp.assert_true((SELECT count(*) = 0 FROM driving_licence), 'account purge cascades snapshots');
SELECT pg_temp.assert_true((SELECT count(*) = 1 FROM audit_event), 'deletion evidence retained');

-- Every FK has a valid index with its columns as the leading index columns.
SELECT pg_temp.assert_true(NOT EXISTS (
    SELECT 1 FROM pg_constraint fk JOIN pg_class t ON t.oid = fk.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE fk.contype = 'f' AND n.nspname = 'public' AND NOT EXISTS (
        SELECT 1 FROM pg_index i WHERE i.indrelid = fk.conrelid AND i.indisvalid
          AND i.indpred IS NULL
          AND (i.indkey::smallint[])[0:cardinality(fk.conkey)-1] =
              (SELECT array_agg(k) FROM unnest(fk.conkey) k)
    )
), 'all foreign keys indexed');
SELECT pg_temp.assert_true(NOT EXISTS (
    SELECT 1 FROM pg_class t JOIN pg_namespace n ON n.oid = t.relnamespace
    JOIN pg_attribute a ON a.attrelid = t.oid
    WHERE n.nspname = 'public' AND t.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
      AND t.relname NOT IN ('databasechangelog', 'databasechangeloglock')
      AND (col_description(t.oid, a.attnum) IS NULL OR obj_description(t.oid, 'pg_class') IS NULL)
), 'every application table and column has a data description');
SELECT pg_temp.assert_true((SELECT obj_description(oid, 'pg_namespace') IS NOT NULL
    FROM pg_namespace WHERE nspname = 'public'), 'application schema has a description');
SELECT pg_temp.assert_true(('ÕUN' COLLATE et_ci = 'õun') AND ('oun' COLLATE et_ci <> 'õun'), 'Estonian case and accent rules');
SELECT pg_temp.assert_true(current_setting('TimeZone') = 'UTC', 'UTC database timezone');
ROLLBACK;
\echo 'Database integration assertions passed (fixtures rolled back).'
