-- Preserve the actual source's category dates and distinguish driving-right deadlines
-- from document expiry. No medical dates are inferred from the licence service.
ALTER TABLE licence_category ADD COLUMN first_issued_on date;
ALTER TABLE licence_category ADD COLUMN expires_on date;
ALTER TABLE licence_category ADD CONSTRAINT category_date_order CHECK (
    first_issued_on IS NULL OR expires_on IS NULL OR first_issued_on <= expires_on
);
ALTER TABLE driving_licence ADD COLUMN expiry_kind varchar(16) NOT NULL DEFAULT 'document'
    CHECK (expiry_kind IN ('document', 'driving_right'));
ALTER TABLE web_push_subscription ADD COLUMN endpoint_hash bytea
    CHECK (endpoint_hash IS NULL OR octet_length(endpoint_hash) = 32);
ALTER TABLE web_push_subscription ADD CONSTRAINT subscription_endpoint_unique UNIQUE (user_id, endpoint_hash);
COMMENT ON COLUMN licence_category.first_issued_on IS 'First category entitlement issue date supplied by the upstream contract; NULL for earlier cache rows.';
COMMENT ON COLUMN licence_category.expires_on IS 'Category entitlement deadline from the source; NULL when not supplied.';
COMMENT ON COLUMN driving_licence.expiry_kind IS 'Whether expires_on describes document expiry or the source driving-right deadline; do not present the latter as a proven document expiry.';
COMMENT ON COLUMN web_push_subscription.endpoint_hash IS 'SHA-256 endpoint fingerprint used for same-user idempotent registration; no usable endpoint secret.';
