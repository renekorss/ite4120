SELECT 1 / CASE WHEN NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name NOT IN ('databasechangelog', 'databasechangeloglock')
) THEN 1 ELSE 0 END AS rollback_removed_application_tables;
