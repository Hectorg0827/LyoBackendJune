-- PostgreSQL initialization script for LyoBackendJune production

-- Create necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- Create full-text search configuration for better search
CREATE TEXT SEARCH CONFIGURATION IF NOT EXISTS english_unaccent (COPY = english);
ALTER TEXT SEARCH CONFIGURATION english_unaccent
  ALTER MAPPING FOR hword, hword_part, word WITH unaccent, english_stem;

-- Create database user for application (if not using default postgres user)
-- DO $$ 
-- BEGIN
--   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'lyoapp') THEN
--     CREATE USER lyoapp WITH PASSWORD 'secure_password_here';
--     GRANT CONNECT ON DATABASE lyodb TO lyoapp;
--     GRANT USAGE ON SCHEMA public TO lyoapp;
--     GRANT CREATE ON SCHEMA public TO lyoapp;
--   END IF;
-- END
-- $$;

-- Set timezone
SET timezone = 'UTC';

-- Performance optimizations
ALTER DATABASE lyodb SET shared_preload_libraries = 'pg_stat_statements';
ALTER DATABASE lyodb SET track_activity_query_size = 2048;
ALTER DATABASE lyodb SET track_io_timing = on;
ALTER DATABASE lyodb SET track_functions = 'all';

-- Create indexes for common query patterns (will be created by SQLAlchemy, but good to have)
-- These will be created automatically by your models, but included for reference

COMMIT;
