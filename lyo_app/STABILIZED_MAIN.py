import time
import os
from fastapi import FastAPI
from lyo_app.enhanced_main import app as base_app
from lyo_app.core.pool_stabilizer import get_stabilized_engine_config
from lyo_app.core.database import engine as db_engine

# This is the NEW stabilized entry point
app = base_app

@app.get("/prod-check")
async def production_check():
    from lyo_app.core.database import engine
    pool = engine.pool
    return {
        "status": "STABILIZED_PROD_V1",
        "pool_config": {
            "size": getattr(pool, "_size", "unknown"),
            "max_overflow": getattr(pool, "_max_overflow", "unknown"),
            "timeout": getattr(pool, "_timeout", "unknown"),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        },
        "engine_type": str(type(engine.pool)),
        "timestamp": time.time()
    }

@app.get("/")
async def root_v2():
    return {
        "message": "LyoBackend STABILIZED PRODUCTION V1",
        "version": "4.0.0-STABLE",
        "diagnostic_url": "/prod-check",
        "timestamp": time.time()
    }

# Overwrite the root of the base app
app.router.routes = [r for r in app.router.routes if r.path != "/"]
app.get("/")(root_v2)
