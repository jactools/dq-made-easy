-- Enable pg_stat_statements so OpenMetadata (and other tools) can query
-- the pg_stat_statements view for query statistics and connection testing.
-- Requires shared_preload_libraries=pg_stat_statements on the server
-- (configured via the 'command' override in docker-compose.yml).
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
