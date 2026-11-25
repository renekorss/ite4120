-- Run as the local bootstrap owner; repeat safely for pre-existing volumes.
\set ON_ERROR_STOP on
\getenv api_password API_DATABASE_PASSWORD
SELECT 'CREATE ROLE reminder_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION IN ROLE reminder_runtime'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reminder_api') \gexec
ALTER ROLE reminder_api PASSWORD :'api_password';
GRANT reminder_runtime TO reminder_api;
