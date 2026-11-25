\set ON_ERROR_STOP on
BEGIN;
CREATE FUNCTION pg_temp.demo_assert(value boolean, label text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    IF value IS DISTINCT FROM true THEN RAISE EXCEPTION 'Demo assertion failed: %', label; END IF;
END $$;
SELECT pg_temp.demo_assert((SELECT count(*) = 7 FROM user_account
    WHERE identity_issuer = 'synthetic-driving-reminder-v1'), 'exactly seven demo accounts');
SELECT pg_temp.demo_assert((SELECT count(*) = 7 FROM latest_successful_check c
    JOIN user_account u ON u.id = c.user_id WHERE u.identity_issuer = 'synthetic-driving-reminder-v1'), 'one current successful snapshot per demo account');
SELECT pg_temp.demo_assert((SELECT driving_status = 'at_risk' FROM latest_successful_check
    WHERE user_id = 'f1000000-0000-4000-8000-000000000003'), 'failed refresh retains at-risk medical snapshot');
SELECT pg_temp.demo_assert((SELECT outcome = 'failed' AND error_code = 'XR_TIMEOUT' FROM status_check
    WHERE id = 'f2000000-0000-4000-8000-000000000203'), 'safe failed-refresh example');
SELECT pg_temp.demo_assert((SELECT driving_status = 'valid' AND status_changed FROM latest_successful_check
    WHERE user_id = 'f1000000-0000-4000-8000-000000000007'), 'renewal changes at-risk to valid');
SELECT pg_temp.demo_assert((SELECT count(*) = 2 FROM latest_successful_check c
    JOIN user_account u ON u.id = c.user_id WHERE u.identity_issuer = 'synthetic-driving-reminder-v1'
    AND c.driving_status = 'invalid'), 'both expired-document scenarios');
SELECT pg_temp.demo_assert(NOT EXISTS (
    SELECT 1 FROM status_check c JOIN user_account u ON u.id = c.user_id
    WHERE u.identity_issuer = 'synthetic-driving-reminder-v1'
      AND (c.xroad_request_id IS NULL OR c.xroad_request_id NOT LIKE 'MOCK-NOT-XROAD-%')
), 'all simulated requests clearly marked');
SELECT pg_temp.demo_assert((SELECT count(*) = 4 FROM notification n JOIN user_account u ON u.id = n.user_id
    WHERE u.identity_issuer = 'synthetic-driving-reminder-v1' AND n.state = 'pending'), 'four upcoming target reminders including both same-date targets');
SELECT pg_temp.demo_assert((SELECT count(*) = 1 FROM notification n JOIN user_account u ON u.id = n.user_id
    WHERE u.identity_issuer = 'synthetic-driving-reminder-v1' AND n.state = 'cancelled'), 'renewal cancels old reminder');
SELECT pg_temp.demo_assert(NOT EXISTS (
    SELECT 1 FROM notification n JOIN status_check c ON c.id = n.check_id
    JOIN user_account u ON u.id = n.user_id WHERE u.identity_issuer = 'synthetic-driving-reminder-v1'
    AND (n.created_at < c.completed_at OR n.sent_at < n.scheduled_at)
), 'historical deliveries follow their snapshots and schedules');
SELECT pg_temp.demo_assert(NOT EXISTS (
    SELECT 1 FROM notification n JOIN notification_attempt a ON a.notification_id = n.id
    JOIN user_account u ON u.id = n.user_id WHERE u.identity_issuer = 'synthetic-driving-reminder-v1'
    AND (a.started_at < n.created_at OR a.completed_at <> n.sent_at)
), 'attempts agree with sent history');
SELECT pg_temp.demo_assert(NOT EXISTS (
    SELECT 1 FROM web_session s JOIN user_account u ON u.id = s.user_id
    WHERE u.identity_issuer = 'synthetic-driving-reminder-v1'
    UNION ALL
    SELECT 1 FROM web_push_subscription s JOIN user_account u ON u.id = s.user_id
    WHERE u.identity_issuer = 'synthetic-driving-reminder-v1'
), 'no usable authentication or delivery secrets seeded');
ROLLBACK;
\echo 'Synthetic demo assertions passed.'
