#!/usr/bin/env python3
import asyncio
import os
import sys
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text, inspect

# Ensure we can import lyo_app
sys.path.insert(0, str(Path(__file__).parent))

from lyo_app.core.config import settings
from lyo_app.core.logging import get_logger

logger = get_logger(__name__)

async def fix_schema():
    db_url = settings.database_url
    if not db_url:
        print("❌ DATABASE_URL not found in settings.")
        return

    # Special handling for local testing if Postgres fails
    is_sqlite = "sqlite" in db_url
    print(f"Connecting to database: {db_url.split('@')[1] if '@' in db_url else db_url}")
    
    engine = create_async_engine(db_url, echo=True)
    async with engine.begin() as conn:
        print("Checking for refresh_tokens table...")
        
        # Check if table exists
        def existing_tables(sync_conn):
            inspector = inspect(sync_conn)
            return inspector.get_table_names()
            
        tables = await conn.run_sync(existing_tables)
        if "refresh_tokens" in tables:
            print("✅ refresh_tokens table ALREADY EXISTS.")
            return

        print("⚠️ Table missing. Creating it now...")
        
        # Database-specific types and defaults
        id_type = "SERIAL PRIMARY KEY" if not is_sqlite else "INTEGER PRIMARY KEY AUTOINCREMENT"
        ts_type = "TIMESTAMP WITH TIME ZONE" if not is_sqlite else "DATETIME"
        now_func = "now()" if not is_sqlite else "CURRENT_TIMESTAMP"
        
        await conn.execute(text(f"""
            CREATE TABLE refresh_tokens (
                id {id_type},
                token VARCHAR(255) NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
                expires_at {ts_type} NOT NULL,
                device_info JSON,
                created_at {ts_type} NOT NULL DEFAULT {now_func}
            )
        """))
        
        # Create Indexes
        await conn.execute(text("CREATE UNIQUE INDEX ix_refresh_tokens_token ON refresh_tokens (token)"))
        await conn.execute(text("CREATE INDEX ix_refresh_tokens_id ON refresh_tokens (id)"))
        await conn.execute(text("CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id)"))
        
        print("✅ refresh_tokens table CREATED SUCCESSFULLY.")

if __name__ == "__main__":
    try:
        asyncio.run(fix_schema())
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
