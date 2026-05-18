import logging
logger = logging.getLogger("lyo.pool_stabilizer")

def get_stabilized_engine_config(base_config: dict) -> dict:
    """Apply async-safe production pool limits without overriding pool classes."""
    if "poolclass" in base_config:
        logger.info("Keeping configured database pool class for this driver")
        return base_config

    logger.info("Applying async-safe database pool limits: size=20, overflow=20, timeout=30s")

    base_config.pop("pool_size", None)
    base_config.pop("max_overflow", None)
    base_config.pop("pool_timeout", None)

    base_config.update({
        "pool_size": 20,
        "max_overflow": 20,
        "pool_timeout": 30.0,
    })

    connect_args = base_config.get("connect_args", {})
    connect_args["command_timeout"] = 30.0
    base_config["connect_args"] = connect_args

    return base_config
