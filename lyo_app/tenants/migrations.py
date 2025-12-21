"""
Database migration script that runs on first request.
Creates multi-tenant tables if they don't exist.
"""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MIGRATION_SQL = """
-- Create organizations table
CREATE TABLE IF NOT EXISTS organizations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    plan_tier VARCHAR(50) NOT NULL DEFAULT 'free',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    contact_email VARCHAR(255),
    monthly_api_calls INTEGER NOT NULL DEFAULT 0,
    monthly_ai_tokens INTEGER NOT NULL DEFAULT 0,
    usage_reset_at TIMESTAMP,
    custom_rate_limit INTEGER,
    custom_ai_limit INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create api_keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    key_prefix VARCHAR(20) NOT NULL,
    key_hash VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at TIMESTAMP,
    total_requests INTEGER NOT NULL DEFAULT 0,
    rate_limit_override INTEGER,
    expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create usage_logs table
CREATE TABLE IF NOT EXISTS usage_logs (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    endpoint VARCHAR(200) NOT NULL,
    method VARCHAR(10) NOT NULL,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    cost_usd FLOAT NOT NULL DEFAULT 0.0,
    status_code INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    api_key_id INTEGER REFERENCES api_keys(id) ON DELETE SET NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_api_keys_org ON api_keys(organization_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_usage_logs_org ON usage_logs(organization_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_created ON usage_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_organizations_slug ON organizations(slug);
"""

ADD_ORG_ID_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'organization_id') THEN
        ALTER TABLE users ADD COLUMN organization_id INTEGER REFERENCES organizations(id);
        CREATE INDEX IF NOT EXISTS idx_users_organization_id ON users(organization_id);
    END IF;
END $$;
"""

ISOLATION_MIGRATION_SQL = """
-- Add organization_id to content tables if they don't have it
DO $$
DECLARE
    tbl text;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'courses', 'lessons', 'course_enrollments', 'lesson_completions',
        'chat_courses', 'chat_notes', 'chat_conversations', 'chat_messages', 'chat_telemetry',
        'posts', 'comments', 'user_follows'
    ] LOOP
        -- Check if table exists first
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = tbl) THEN
            -- Check if column exists
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = tbl AND column_name = 'organization_id') THEN
                
                -- Add column with default 1 (Lyo Inc) and foreign key
                EXECUTE format('ALTER TABLE %I ADD COLUMN organization_id INTEGER NOT NULL DEFAULT 1 REFERENCES organizations(id)', tbl);
                
                -- Add index
                EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%I_organization_id ON %I(organization_id)', tbl, tbl);
                
                RAISE NOTICE 'Added organization_id to %', tbl;
            END IF;
        END IF;
    END LOOP;
END $$;
"""

STORAGE_MIGRATION_SQL = """
-- Create file_assets table for multi-tenant storage tracking
CREATE TABLE IF NOT EXISTS file_assets (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_path VARCHAR(500) UNIQUE NOT NULL,
    url VARCHAR(1000) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(100),
    size_bytes INTEGER NOT NULL DEFAULT 0,
    is_private BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_file_assets_org ON file_assets(organization_id);
CREATE INDEX IF NOT EXISTS idx_file_assets_user ON file_assets(user_id);
"""
async def run_tenant_migrations(db: AsyncSession) -> bool:
    """
    Run multi-tenant migrations. Safe to call multiple times (idempotent).
    
    Returns True if migrations were run, False if they were skipped or failed.
    """
    try:
        # 1. Create base tables (organizations, api_keys, usage_logs)
        result = await db.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'organizations')"
        ))
        tables_exist = result.scalar()
        
        if not tables_exist:
            logger.info("Running base multi-tenant table migrations...")
            for statement in MIGRATION_SQL.strip().split(';'):
                if statement.strip():
                    await db.execute(text(statement))
        
        # 2. Add organization_id to users
        await db.execute(text(ADD_ORG_ID_SQL))
        
        # 3. Add organization_id to content tables (Data Isolation)
        await db.execute(text(ISOLATION_MIGRATION_SQL))
        
        # 4. Create file_assets table (Storage)
        await db.execute(text(STORAGE_MIGRATION_SQL))
        
        await db.commit()
        logger.info("✅ Multi-tenant migrations (including data isolation) completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        await db.rollback()
        return False
