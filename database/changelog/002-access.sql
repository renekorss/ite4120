GRANT USAGE ON SCHEMA public TO reminder_runtime, reminder_retention, reminder_auditor;
GRANT SELECT, INSERT, UPDATE ON user_account, web_session, status_check,
    reminder_preference, reminder_interval, web_push_subscription,
    notification, notification_attempt TO reminder_runtime;
GRANT DELETE ON web_session, reminder_interval TO reminder_runtime;
GRANT SELECT, INSERT ON driving_licence, licence_category, medical_certificate TO reminder_runtime;
GRANT SELECT ON latest_successful_check TO reminder_runtime;
GRANT INSERT ON audit_event TO reminder_runtime;
GRANT SELECT ON audit_event TO reminder_auditor;
-- Only a separately controlled retention operator may purge data. Audit retention
-- is deliberately excluded and requires the independent audit custodian.
GRANT SELECT, DELETE ON user_account, web_session, status_check, driving_licence,
    licence_category, medical_certificate, reminder_preference, reminder_interval,
    web_push_subscription, notification, notification_attempt TO reminder_retention;
