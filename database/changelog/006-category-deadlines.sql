-- Retain the original snapshot/date constraints for both kinds of licence deadline.
ALTER TABLE driving_licence ADD UNIQUE (check_id, id);
ALTER TABLE licence_category ADD UNIQUE (licence_id, category_code, expires_on);
ALTER TABLE notification
    DROP CONSTRAINT notification_check_id_licence_id_expires_on_fkey,
    ADD COLUMN category_code varchar(4),
    ADD COLUMN document_expires_on date GENERATED ALWAYS AS
        (CASE WHEN category_code IS NULL THEN expires_on END) STORED,
    ADD CHECK (category_code IS NULL OR licence_id IS NOT NULL),
    ADD FOREIGN KEY (check_id, licence_id) REFERENCES driving_licence(check_id, id),
    ADD FOREIGN KEY (check_id, licence_id, document_expires_on) REFERENCES driving_licence(check_id, id, expires_on),
    ADD FOREIGN KEY (licence_id, category_code, expires_on) REFERENCES licence_category(licence_id, category_code, expires_on);
COMMENT ON COLUMN notification.category_code IS 'Licence category when this deadline comes from a category entitlement.';
COMMENT ON COLUMN notification.document_expires_on IS 'Generated document-level date reference for notices without a category.';
CREATE INDEX notification_document_deadline_idx ON notification(check_id, licence_id, document_expires_on);
CREATE INDEX notification_category_deadline_idx ON notification(licence_id, category_code, expires_on);
