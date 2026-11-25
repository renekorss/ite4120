-- Refuse rollback if a category-only deadline cannot be represented in the old schema.
ALTER TABLE notification
    ADD FOREIGN KEY (check_id, licence_id, expires_on) REFERENCES driving_licence(check_id, id, expires_on),
    DROP CONSTRAINT notification_check_id_licence_id_fkey,
    DROP COLUMN document_expires_on,
    DROP COLUMN category_code;
ALTER TABLE licence_category DROP CONSTRAINT licence_category_licence_id_category_code_expires_on_key;
ALTER TABLE driving_licence DROP CONSTRAINT driving_licence_check_id_id_key;
