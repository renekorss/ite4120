-- All application relations live in public; Liquibase owns its metadata separately.
-- Human-language text uses Estonian, case-insensitive, accent-sensitive collation.
CREATE COLLATION et_ci (provider = icu, locale = 'et-EE-u-ks-level2', deterministic = false);

CREATE TABLE user_account (
    id uuid PRIMARY KEY,
    identity_issuer varchar(255) NOT NULL,
    identity_subject varchar(255) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at timestamptz,
    CONSTRAINT user_identity_unique UNIQUE (identity_issuer, identity_subject),
    CONSTRAINT user_deleted_after_created CHECK (deleted_at IS NULL OR deleted_at >= created_at),
    CONSTRAINT user_identity_not_empty CHECK (length(identity_issuer) > 0 AND length(identity_subject) > 0)
);

CREATE TABLE web_session (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
    token_hash bytea NOT NULL UNIQUE CHECK (octet_length(token_hash) = 32),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK (expires_at > created_at),
    CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);
CREATE INDEX session_user_idx ON web_session(user_id);
CREATE INDEX session_expiry_idx ON web_session(expires_at);

CREATE TABLE status_check (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
    requested_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamptz,
    outcome varchar(12) NOT NULL CHECK (outcome IN ('pending', 'successful', 'failed')),
    trace_id uuid NOT NULL,
    xroad_request_id varchar(255),
    source_code varchar(40) NOT NULL DEFAULT 'transport_administration_xroad'
        CHECK (source_code = 'transport_administration_xroad'),
    driving_status varchar(12) CHECK (driving_status IN ('valid', 'at_risk', 'invalid')),
    reason_code varchar(64),
    medical_requirement varchar(16) CHECK (medical_requirement IN ('required', 'not_required', 'unknown')),
    status_changed boolean,
    error_code varchar(64),
    UNIQUE (user_id, id),
    UNIQUE (id, outcome),
    CHECK (completed_at IS NULL OR completed_at >= requested_at),
    CONSTRAINT check_result_shape CHECK (
        (outcome = 'pending' AND completed_at IS NULL AND driving_status IS NULL
            AND reason_code IS NULL AND medical_requirement IS NULL AND status_changed IS NULL AND error_code IS NULL)
        OR (outcome = 'failed' AND completed_at IS NOT NULL AND error_code IS NOT NULL
            AND driving_status IS NULL AND reason_code IS NULL AND medical_requirement IS NULL AND status_changed IS NULL)
        OR (outcome = 'successful' AND completed_at IS NOT NULL AND driving_status IS NOT NULL
            AND medical_requirement IS NOT NULL AND error_code IS NULL
            AND (driving_status = 'valid' OR reason_code IS NOT NULL))
    )
);
CREATE INDEX check_history_idx ON status_check(user_id, completed_at DESC, id DESC);
CREATE INDEX check_pending_idx ON status_check(outcome, requested_at);

CREATE TABLE driving_licence (
    id uuid PRIMARY KEY,
    check_id uuid NOT NULL,
    check_outcome varchar(12) NOT NULL DEFAULT 'successful' CHECK (check_outcome = 'successful'),
    document_status varchar(16) NOT NULL CHECK (document_status IN ('valid', 'expired', 'revoked', 'suspended', 'unknown')),
    issued_on date,
    expires_on date,
    FOREIGN KEY (check_id, check_outcome) REFERENCES status_check(id, outcome) ON DELETE CASCADE,
    UNIQUE (check_id, id, expires_on),
    CHECK (issued_on IS NULL OR expires_on IS NULL OR expires_on >= issued_on)
);
CREATE INDEX licence_check_idx ON driving_licence(check_id, check_outcome);

CREATE TABLE licence_category (
    licence_id uuid NOT NULL REFERENCES driving_licence(id) ON DELETE CASCADE,
    category_code varchar(4) NOT NULL CHECK (category_code IN
        ('AM', 'A1', 'A2', 'A', 'B1', 'B', 'BE', 'C1', 'C1E', 'C', 'CE', 'D1', 'D1E', 'D', 'DE', 'T')),
    PRIMARY KEY (licence_id, category_code)
);

CREATE TABLE medical_certificate (
    id uuid PRIMARY KEY,
    check_id uuid NOT NULL,
    check_outcome varchar(12) NOT NULL DEFAULT 'successful' CHECK (check_outcome = 'successful'),
    certificate_status varchar(16) NOT NULL CHECK (certificate_status IN ('valid', 'expired', 'revoked', 'unknown')),
    issued_on date,
    expires_on date,
    FOREIGN KEY (check_id, check_outcome) REFERENCES status_check(id, outcome) ON DELETE CASCADE,
    UNIQUE (check_id, id, expires_on),
    CHECK (issued_on IS NULL OR expires_on IS NULL OR expires_on >= issued_on)
);
CREATE INDEX medical_check_idx ON medical_certificate(check_id, check_outcome);

CREATE TABLE reminder_preference (
    user_id uuid PRIMARY KEY REFERENCES user_account(id) ON DELETE CASCADE,
    enabled boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE reminder_interval (
    user_id uuid NOT NULL REFERENCES reminder_preference(user_id) ON DELETE CASCADE,
    days_before smallint NOT NULL CHECK (days_before IN (90, 30, 7)),
    PRIMARY KEY (user_id, days_before)
);

CREATE TABLE web_push_subscription (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
    encrypted_subscription bytea NOT NULL CHECK (octet_length(encrypted_subscription) > 0),
    encryption_key_ref varchar(128) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at timestamptz,
    UNIQUE (user_id, id),
    CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);

-- Durable outbox and bounded sent history. A cancelled item can be re-queued;
-- the semantic key survives refresh snapshots and retries.
CREATE TABLE notification (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
    check_id uuid NOT NULL,
    document_kind varchar(24) NOT NULL CHECK (document_kind IN ('driving_licence', 'medical_certificate')),
    licence_id uuid,
    medical_certificate_id uuid,
    expires_on date NOT NULL,
    days_before smallint NOT NULL CHECK (days_before IN (90, 30, 7)),
    scheduled_at timestamptz NOT NULL,
    channel varchar(12) NOT NULL CHECK (channel IN ('in_app', 'web_push')),
    subscription_id uuid,
    state varchar(12) NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'processing', 'sent', 'failed', 'cancelled')),
    claimed_until timestamptz,
    sent_at timestamptz,
    error_code varchar(64),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id, check_id) REFERENCES status_check(user_id, id) ON DELETE NO ACTION,
    FOREIGN KEY (check_id, licence_id, expires_on) REFERENCES driving_licence(check_id, id, expires_on) ON DELETE NO ACTION,
    FOREIGN KEY (check_id, medical_certificate_id, expires_on) REFERENCES medical_certificate(check_id, id, expires_on) ON DELETE NO ACTION,
    FOREIGN KEY (user_id, subscription_id) REFERENCES web_push_subscription(user_id, id) ON DELETE NO ACTION,
    UNIQUE (user_id, document_kind, expires_on, days_before),
    CHECK ((document_kind = 'driving_licence' AND licence_id IS NOT NULL AND medical_certificate_id IS NULL)
        OR (document_kind = 'medical_certificate' AND medical_certificate_id IS NOT NULL AND licence_id IS NULL)),
    CHECK ((channel = 'web_push' AND subscription_id IS NOT NULL) OR (channel = 'in_app' AND subscription_id IS NULL)),
    CHECK ((state = 'sent') = (sent_at IS NOT NULL)),
    CHECK ((state = 'processing') = (claimed_until IS NOT NULL)),
    CHECK (state <> 'failed' OR error_code IS NOT NULL),
    CHECK (sent_at IS NULL OR sent_at >= created_at)
);
CREATE INDEX notification_check_idx ON notification(user_id, check_id);
CREATE INDEX notification_licence_idx ON notification(check_id, licence_id, expires_on);
CREATE INDEX notification_medical_idx ON notification(check_id, medical_certificate_id, expires_on);
CREATE INDEX notification_subscription_idx ON notification(user_id, subscription_id);
CREATE INDEX notification_due_idx ON notification(state, scheduled_at);
CREATE INDEX notification_history_idx ON notification(user_id, sent_at DESC, id DESC);

CREATE TABLE notification_attempt (
    id uuid PRIMARY KEY,
    notification_id uuid NOT NULL REFERENCES notification(id) ON DELETE CASCADE,
    attempt_number smallint NOT NULL CHECK (attempt_number > 0),
    started_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamptz,
    outcome varchar(12) NOT NULL CHECK (outcome IN ('pending', 'successful', 'failed', 'unknown')),
    error_code varchar(64),
    trace_id uuid NOT NULL,
    UNIQUE (notification_id, attempt_number),
    CHECK (completed_at IS NULL OR completed_at >= started_at),
    CHECK ((outcome = 'pending') = (completed_at IS NULL)),
    CHECK (outcome NOT IN ('failed', 'unknown') OR error_code IS NOT NULL)
);

CREATE TABLE audit_event (
    id uuid PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor_user_id uuid REFERENCES user_account(id) ON DELETE NO ACTION,
    subject_user_id uuid REFERENCES user_account(id) ON DELETE NO ACTION,
    actor_kind varchar(12) NOT NULL CHECK (actor_kind IN ('user', 'operator', 'system', 'anonymous')),
    action_code varchar(64) NOT NULL,
    outcome varchar(12) NOT NULL CHECK (outcome IN ('success', 'failure', 'unknown')),
    error_code varchar(64),
    trace_id uuid NOT NULL,
    CHECK (actor_kind <> 'user' OR actor_user_id IS NOT NULL),
    CHECK (outcome <> 'failure' OR error_code IS NOT NULL)
);
CREATE INDEX audit_actor_idx ON audit_event(actor_user_id, occurred_at);
CREATE INDEX audit_subject_idx ON audit_event(subject_user_id, occurred_at);
CREATE INDEX audit_retention_idx ON audit_event(occurred_at);

CREATE VIEW latest_successful_check AS
SELECT c.* FROM status_check c
WHERE c.outcome = 'successful' AND NOT EXISTS (
    SELECT 1 FROM status_check newer
    WHERE newer.user_id = c.user_id AND newer.outcome = 'successful'
      AND (newer.completed_at > c.completed_at
        OR (newer.completed_at = c.completed_at AND newer.id > c.id))
);

COMMENT ON TABLE user_account IS 'Local account: opaque external identity only; no name, national ID, email or password.';
COMMENT ON TABLE web_session IS 'Shared web sessions; hash a high-entropy token with a maintained library; never store the bearer token.';
COMMENT ON TABLE status_check IS 'Local X-Road request history. Successful rows identify immutable cached snapshots, never authoritative registry records.';
COMMENT ON COLUMN status_check.driving_status IS 'Local normalized assessment, not legal proof of entitlement to drive.';
COMMENT ON COLUMN status_check.reason_code IS 'Safe translation key for an assessment reason; never raw upstream text.';
COMMENT ON COLUMN status_check.status_changed IS 'NULL for the first success; otherwise compare driving_status with previous success while holding the user lock.';
COMMENT ON COLUMN status_check.medical_requirement IS 'Unknown is distinct from not required; absence of a certificate alone proves neither.';
COMMENT ON TABLE driving_licence IS 'Minimized licence cache for one successful check; source is inherited through check_id.';
COMMENT ON TABLE licence_category IS 'Category membership within a cached licence; category-specific validity requires the future contract.';
COMMENT ON TABLE medical_certificate IS 'Certificate status and dates only; no diagnoses, examination results, physician or document number.';
COMMENT ON TABLE reminder_preference IS 'Local opt-in; provision with 90/30/7 interval rows atomically when creating an account.';
COMMENT ON TABLE reminder_interval IS 'Selected supported lead times; zero rows means no selected intervals.';
COMMENT ON TABLE web_push_subscription IS 'Optional browser Web Push delivery secret bundle encrypted outside the database; not mobile push.';
COMMENT ON TABLE notification IS 'Local delivery event/outbox. Expiry and target reference are historical evidence; do not rewrite sent events.';
COMMENT ON TABLE notification_attempt IS 'Safe delivery outcomes and trace IDs; no endpoint, request body or upstream error text.';
COMMENT ON TABLE audit_event IS 'Append-only for runtime. Pseudonymous references remain personal data. External protected audit sink required before production.';
