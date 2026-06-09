"""
GDPR / CCPA / App Store account-deletion support.

App Store guideline 5.1.1(v) requires that an account created in-app can be
deleted from in-app. Two correct implementations exist:

* **Anonymization** (default, ``anonymize_user_account``): scrub every piece of
  personal data from the user row, revoke all sessions, and deactivate the
  account so it can no longer be logged into or linked to a real person. This
  is FK-safe regardless of how the ~100 ``users.id`` foreign keys are
  configured, so it always succeeds.

* **Hard delete** (``purge_user_data``): physically remove the user row and
  every row that references it. This is only safe once the user-referencing
  foreign keys declare ``ON DELETE CASCADE`` (or the DB role can disable FK
  enforcement); otherwise PostgreSQL raises a foreign-key violation when other
  users' rows (e.g. a reply on the user's post) still reference the user's
  content. It is provided for that future migration and for test/SQLite use.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict

from sqlalchemy import delete as sa_delete, or_
from sqlalchemy.exc import CircularDependencyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def anonymize_user_account(db: AsyncSession, user_id: int) -> Dict[str, int]:
    """Irreversibly anonymize a user and revoke their access.

    Scrubs all personal data from the user row, makes the account unable to log
    in, and deletes refresh tokens. Runs inside the caller's transaction (the
    caller commits). Returns a small summary for logging/audit.

    This is the default, foreign-key-safe account-deletion mechanism: it only
    mutates the user row and deletes leaf token rows, so it cannot raise a
    foreign-key violation no matter how the schema's user references are set up.
    """
    from lyo_app.auth.models import User

    user = await db.get(User, user_id)
    if user is None:
        return {"users_anonymized": 0}

    placeholder = f"deleted_user_{user_id}"

    # Overwrite every identifying/personal field. getattr/hasattr guards keep
    # this resilient as the model evolves.
    user.email = f"deleted+{user_id}@deleted.invalid"
    user.username = placeholder
    # Block login: store a non-verifying hash sentinel rather than a real hash.
    user.hashed_password = "!"  # bcrypt/argon never produce a bare "!"
    for field in (
        "first_name", "last_name", "bio", "avatar_url",
        "firebase_uid", "auth_provider", "learning_profile",
        "user_context_summary", "last_login",
    ):
        if hasattr(user, field):
            setattr(user, field, None)
    if hasattr(user, "is_active"):
        user.is_active = False
    if hasattr(user, "is_verified"):
        user.is_verified = False
    if hasattr(user, "is_superuser"):
        user.is_superuser = False
    if hasattr(user, "updated_at"):
        user.updated_at = datetime.utcnow()

    summary: Dict[str, int] = {"users_anonymized": 1}

    # Revoke all active sessions (FK-safe: refresh_tokens is a leaf table).
    try:
        from lyo_app.auth.models import RefreshToken
        result = await db.execute(
            sa_delete(RefreshToken).where(RefreshToken.user_id == user_id)
        )
        summary["refresh_tokens_revoked"] = result.rowcount or 0
    except Exception as e:  # noqa: BLE001 - token model/table optional
        logger.warning(f"Could not revoke refresh tokens for user {user_id}: {e}")

    logger.info(f"Anonymized account for user {user_id}")
    return summary


# ---------------------------------------------------------------------------
# Hard delete (opt-in; requires cascading FKs or FK enforcement disabled)
# ---------------------------------------------------------------------------

def _user_fk_columns(table, users_table):
    cols = []
    for col in table.columns:
        for fk in col.foreign_keys:
            try:
                if fk.column.table is users_table:
                    cols.append(col)
                    break
            except Exception:  # noqa: BLE001 - unresolved FK target
                continue
    return cols


def _deletion_ordered_tables(metadata, users_table):
    try:
        return list(reversed(metadata.sorted_tables))
    except CircularDependencyError:
        logger.warning("Schema has a FK cycle; using unordered table deletion")
        return list(metadata.tables.values())


async def purge_user_data(db: AsyncSession, user_id: int) -> Dict[str, int]:
    """Physically delete the user and every row that references them.

    Deletes children before parents. NOTE: only safe when user-referencing FKs
    cascade or FK enforcement is disabled — otherwise other users' rows that
    reference this user's content will cause a foreign-key violation. Prefer
    :func:`anonymize_user_account` unless those guarantees hold.
    """
    from lyo_app.core.database import Base
    from lyo_app.auth.models import User

    users_table = User.__table__
    deleted: Dict[str, int] = {}

    for table in _deletion_ordered_tables(Base.metadata, users_table):
        if table is users_table:
            continue
        fk_cols = _user_fk_columns(table, users_table)
        if not fk_cols:
            continue
        condition = or_(*[col == user_id for col in fk_cols])
        result = await db.execute(sa_delete(table).where(condition))
        if result.rowcount:
            deleted[table.name] = result.rowcount

    result = await db.execute(
        sa_delete(users_table).where(users_table.c.id == user_id)
    )
    deleted["users"] = result.rowcount
    logger.info(f"Hard-purged user {user_id}: {sum(deleted.values())} rows")
    return deleted
