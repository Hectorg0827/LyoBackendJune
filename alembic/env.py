from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import Base and models for autogenerate support
from lyo_app.core.database import Base

# Import all models to ensure they're registered with Base
# Note: Import from .models directly to avoid circular imports through __init__.py
from lyo_app.auth.models import User  # noqa: F401
from lyo_app.learning.models import Course, Lesson, CourseEnrollment, LessonCompletion  # noqa: F401
from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow, FeedItem, UserPostInteraction  # noqa: F401
# Import community models directly to avoid circular imports
import lyo_app.community.models  # noqa: F401
from lyo_app.gamification.models import UserXP, Achievement, UserAchievement, Streak, UserLevel, LeaderboardEntry, Badge, UserBadge  # noqa: F401
# from lyo_app.resources.models import EducationalResource, ResourceTag, CourseResource, ResourceCollection  # noqa: F401
import lyo_app.ai_agents.models  # noqa: F401
# import lyo_app.adaptive_learning.models  # noqa: F401 - module is empty
import lyo_app.ai_study.models  # noqa: F401
import lyo_app.collaboration.models  # noqa: F401
import lyo_app.affect.models  # noqa: F401
# import lyo_app.gen_curriculum.models  # noqa: F401 - has duplicate Lesson table
from lyo_app.stack.models import StackItem  # noqa: F401
from lyo_app.classroom.models import ClassroomSession  # noqa: F401
# AI Classroom - Graph-based Learning Engine
from lyo_app.ai_classroom.models import (  # noqa: F401
    GraphCourse, LearningNode, LearningEdge, Concept, Misconception,
    MasteryState, ReviewSchedule, InteractionAttempt, CourseProgress,
    CelebrationConfig, AdPlacementConfig
)

target_metadata = Base.metadata

# Get database URL from environment, but convert async URL to sync for alembic
def get_url():
    """Get database URL, converting async to sync for migrations."""
    from lyo_app.core.config import settings
    url = settings.database_url
    if url.startswith("postgresql+asyncpg://"):
        # Convert async URL to sync for alembic
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    elif url.startswith("sqlite+aiosqlite://"):
        # Convert async SQLite to sync for alembic
        url = url.replace("sqlite+aiosqlite://", "sqlite://")
    return url

# Set the database URL for alembic
config.set_main_option("sqlalchemy.url", get_url())

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
