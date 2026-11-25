ALTER TABLE web_push_subscription DROP CONSTRAINT subscription_endpoint_unique;
ALTER TABLE web_push_subscription DROP COLUMN endpoint_hash;
ALTER TABLE driving_licence DROP COLUMN expiry_kind;
ALTER TABLE licence_category DROP CONSTRAINT category_date_order;
ALTER TABLE licence_category DROP COLUMN expires_on;
ALTER TABLE licence_category DROP COLUMN first_issued_on;
