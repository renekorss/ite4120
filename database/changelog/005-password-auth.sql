CREATE TABLE password_credential (
    user_id uuid PRIMARY KEY REFERENCES user_account(id) ON DELETE CASCADE,
    username varchar(64) NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9][a-z0-9._-]{2,63}$'),
    password_hash varchar(512) NOT NULL CHECK (length(password_hash) > 20),
    display_name varchar(80) COLLATE et_ci NOT NULL,
    is_enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (updated_at >= created_at)
);
CREATE TABLE login_throttle (
    bucket_hash bytea PRIMARY KEY CHECK (octet_length(bucket_hash) = 32),
    attempts smallint NOT NULL CHECK (attempts > 0),
    expires_at timestamptz NOT NULL
);
CREATE INDEX login_throttle_expiry_idx ON login_throttle(expires_at);
GRANT SELECT ON password_credential TO reminder_runtime;
GRANT UPDATE (password_hash, updated_at) ON password_credential TO reminder_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON login_throttle TO reminder_runtime;
GRANT SELECT, DELETE ON login_throttle TO reminder_retention;
COMMENT ON TABLE password_credential IS 'Normal local password authentication; seeded accounts use the same verifier as any other provisioned account.';
COMMENT ON COLUMN password_credential.user_id IS 'Owning account UUID, indexed by the primary key; credentials are removed with account purge.';
COMMENT ON COLUMN password_credential.username IS 'Canonical lowercase ASCII login name; never an email or national identity number by default.';
COMMENT ON COLUMN password_credential.password_hash IS 'Variable-length encoded Argon2id hash with algorithm parameters and unique salt; never a plaintext password.';
COMMENT ON COLUMN password_credential.display_name IS 'Minimal human-readable profile label using Estonian case-insensitive accent-sensitive collation.';
COMMENT ON COLUMN password_credential.is_enabled IS 'Operator-controlled credential activation; checked at login and on every authenticated request.';
COMMENT ON COLUMN password_credential.created_at IS 'UTC credential provisioning instant.';
COMMENT ON COLUMN password_credential.updated_at IS 'UTC password-hash change instant, including transparent algorithm-cost upgrades.';
COMMENT ON TABLE login_throttle IS 'Short-lived database-backed account/source throttling, shared by API instances; HMAC identifiers only.';
COMMENT ON COLUMN login_throttle.bucket_hash IS 'HMAC-SHA256 of a scoped canonical username or socket source address; key is external, raw values are not persisted.';
COMMENT ON COLUMN login_throttle.attempts IS 'Attempts within the current window, bounded to prevent counter overflow.';
COMMENT ON COLUMN login_throttle.expires_at IS 'UTC expiry of the rate-limit window; expired rows are removed on subsequent login attempts or by retention operations.';
-- Invalidate all tokens previously issued by the account-picker implementation.
-- Rolling back the schema must never silently re-enable these revoked tokens.
WITH revoked AS (
    UPDATE web_session SET revoked_at=clock_timestamp() WHERE revoked_at IS NULL RETURNING user_id
)
INSERT INTO audit_event(id,subject_user_id,actor_kind,action_code,outcome,trace_id)
SELECT gen_random_uuid(),user_id,'system','session.authentication_migrated','success',gen_random_uuid()
FROM revoked;
