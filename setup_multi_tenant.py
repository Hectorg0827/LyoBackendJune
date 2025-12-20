"""
One-time script to create multi-tenant SaaS tables and set up Lyo Inc organization.
Run this script to migrate the database and create the first organization.
"""

import asyncio
import hashlib
import secrets
import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


# SQL to create tables
CREATE_TABLES_SQL = """
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

ADD_ORG_ID_TO_USERS_SQL = """
-- Add organization_id column to users table if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'organization_id') THEN
        ALTER TABLE users ADD COLUMN organization_id INTEGER REFERENCES organizations(id);
        CREATE INDEX IF NOT EXISTS idx_users_organization_id ON users(organization_id);
    END IF;
END $$;
"""


def generate_api_key():
    """Generate API key and hash."""
    raw_key = secrets.token_urlsafe(32)
    full_key = f"lyo_sk_live_{raw_key}"
    key_prefix = full_key[:20]
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, key_prefix, key_hash


async def main():
    # Get database URL from environment or config
    try:
        from lyo_app.core.config import settings
        database_url = settings.DATABASE_URL
    except:
        database_url = os.environ.get("DATABASE_URL")
    
    if not database_url:
        print("❌ DATABASE_URL not found!")
        return
    
    print(f"📦 Connecting to database...")
    
    # Create engine
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            # Step 1: Create tables
            print("📋 Creating multi-tenant tables...")
            for statement in CREATE_TABLES_SQL.strip().split(';'):
                if statement.strip():
                    await session.execute(text(statement))
            await session.commit()
            print("✅ Tables created: organizations, api_keys, usage_logs")
            
            # Step 2: Add organization_id to users
            print("📋 Adding organization_id to users table...")
            await session.execute(text(ADD_ORG_ID_TO_USERS_SQL))
            await session.commit()
            print("✅ Users table updated with organization_id")
            
            # Step 3: Check if Lyo Inc already exists
            result = await session.execute(
                text("SELECT id FROM organizations WHERE slug = 'lyo-inc'")
            )
            existing = result.fetchone()
            
            if existing:
                print(f"ℹ️  Lyo Inc organization already exists (id={existing[0]})")
                org_id = existing[0]
            else:
                # Step 4: Create Lyo Inc organization
                print("🏢 Creating Lyo Inc organization...")
                result = await session.execute(
                    text("""
                        INSERT INTO organizations (name, slug, plan_tier, contact_email, is_active)
                        VALUES ('Lyo Inc', 'lyo-inc', 'enterprise', 'hector.garcia0827@gmail.com', TRUE)
                        RETURNING id
                    """)
                )
                org_id = result.fetchone()[0]
                await session.commit()
                print(f"✅ Created Lyo Inc organization (id={org_id})")
            
            # Step 5: Generate API key
            full_key, key_prefix, key_hash = generate_api_key()
            
            # Check if key already exists
            result = await session.execute(
                text("SELECT id FROM api_keys WHERE organization_id = :org_id AND name = 'Lyo iOS App Key'"),
                {"org_id": org_id}
            )
            existing_key = result.fetchone()
            
            if existing_key:
                print(f"ℹ️  Lyo iOS App Key already exists (id={existing_key[0]})")
                print("⚠️  Generating a new key anyway...")
            
            # Create new API key
            await session.execute(
                text("""
                    INSERT INTO api_keys (organization_id, key_prefix, key_hash, name, description, is_active)
                    VALUES (:org_id, :key_prefix, :key_hash, 'Lyo iOS App Key', 'Auto-generated for Lyo iOS app', TRUE)
                """),
                {"org_id": org_id, "key_prefix": key_prefix, "key_hash": key_hash}
            )
            await session.commit()
            
            print(f"\n{'='*60}")
            print("🎉 SETUP COMPLETE!")
            print(f"{'='*60}")
            print(f"\n📱 YOUR API KEY (save this - shown only once!):")
            print(f"\n    {full_key}\n")
            print(f"{'='*60}")
            print("\n📋 Next steps:")
            print("   1. Copy the API key above")
            print("   2. Add it to iOS app's AppConfig.swift:")
            print('      static let apiKey = "' + full_key + '"')
            print("   3. Add X-API-Key header to all API requests")
            print(f"{'='*60}\n")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
