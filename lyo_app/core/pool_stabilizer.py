import logging
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import pool

logger = logging.getLogger("lyo.pool_stabilizer")

def get_stabilized_engine_config(base_config: dict) -> dict:
    """Forces 20/20 pool settings regardless of what the config files say."""
    logger.info("🛠️ HIJACKING Database Pool: Forcing size=20, overflow=20, timeout=30s")
    
    # Remove any existing pool settings to avoid conflicts
    base_config.pop("pool_size", None)
    base_config.pop("max_overflow", None)
    base_config.pop("pool_timeout", None)
    
    # Inject forced settings
    base_config.update({
        "pool_size": 20,
        "max_overflow": 20,
        "pool_timeout": 30.0,
        "poolclass": pool.QueuePool,
    })
    
    # Force timeout in connect_args for asyncpg
    connect_args = base_config.get("connect_args", {})
    connect_args["command_timeout"] = 30.0
    base_config["connect_args"] = connect_args
    
    return base_config
