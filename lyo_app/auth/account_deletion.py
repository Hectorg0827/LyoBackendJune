"""Permanently delete an account and the personal data that belongs to it.

The schema has grown to well over a hundred tables, some made by migrations
and some only by ``create_all`` at startup, and dozens of them point at a
user, with a foreign key or with a bare ``user_id`` column. A hand-kept list
of tables would fall behind the first time a feature adds one, so the live
database is read at deletion time instead:

* every row that names the user (a foreign key to ``users.id``, or a column
  called ``user_id`` / ``*_user_id`` without one) is deleted, after the rows
  that depend on it;
* a nullable link that only records the user acting on someone else's row
  (``moderated_by_id``, ``reviewed_by_id``, ``invited_by_id``...) is set to
  NULL, so other people's data stays;
* the ``users`` row goes last, in the same transaction. Every access and
  refresh token then fails, because each request looks the user up.

Files the user uploaded through ``/api/v1/media/upload`` are found in the
rows being deleted (avatar, clips, posts, chat attachments...) and deleted
from storage once the database part is committed, unless a row that is left
still links to one. Uploads have no owner record, so a URL in the deleted
rows does not prove the file was theirs: anyone can paste another learner's
avatar URL into a post, and deleting that account must not take the avatar. The Firebase account, if
any, is deleted last, so the same Apple or Google sign-in cannot open the old
account again.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

USERS_TABLE = "users"
# Deeper chains than this (row -> row that depends on it -> ...) do not exist
# today; stopping keeps a reference cycle from recursing forever.
MAX_DEPTH = 8

# A nullable link to users.id with one of these names says whose row it is
# (a view, a like): the row goes with the user. Any other nullable link only
# records them acting on somebody else's row, and is cleared instead.
_OWNER_COLUMN = re.compile(
    r"^(?:\w+_)?(?:user|author|owner|sender|creator|uploader|viewer|reporter|follower|following"
    r"|blocker|blocked|student|learner|instructor|organizer|participant|recipient|receiver)(?:_id)?$"
)
# A column holding a user id without a foreign key (chat and analytics tables).
_LOOSE_USER_COLUMN = re.compile(r"^(?:\w+_)?user_id$")
# Files this API stored: /api/v1/media/upload names each one with a random
# 32-hex name, so nothing else can match.
_MEDIA_URL = re.compile(r"/api/v1/media/file/([a-z0-9_-]{1,64})/([a-f0-9]{32}\.[a-z0-9]{2,5})")


@dataclass(frozen=True)
class _Ref:
    table: str
    column: str
    referred: str
    nullable: bool


class _Schema:
    """Foreign keys and columns of the live database."""

    def __init__(self, conn: Connection):
        inspector = sa.inspect(conn)
        self.columns: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for (_schema, table), cols in inspector.get_multi_columns().items():
            self.columns[table] = {col["name"]: col for col in cols}
        self.children: Dict[str, List[_Ref]] = {}
        for (_schema, table), fks in inspector.get_multi_foreign_keys().items():
            for fk in fks:
                if len(fk["constrained_columns"]) != 1:
                    logger.warning("Account deletion skips composite foreign key %s on %s", fk.get("name"), table)
                    continue
                column = fk["constrained_columns"][0]
                self.children.setdefault(fk["referred_table"], []).append(_Ref(
                    table=table,
                    column=column,
                    referred=fk["referred_columns"][0],
                    nullable=bool(self.columns.get(table, {}).get(column, {}).get("nullable", True)),
                ))
        self._tables: Dict[str, sa.TableClause] = {}

    def table(self, name: str) -> sa.TableClause:
        if name not in self._tables:
            self._tables[name] = sa.table(name, *(sa.column(col) for col in self.columns[name]))
        return self._tables[name]

    def text_columns(self, name: str) -> List[str]:
        return [
            col for col, info in self.columns[name].items()
            if isinstance(info["type"], (sa.String, sa.Text, sa.JSON))
            or type(info["type"]).__name__.upper() in {"JSON", "JSONB"}
        ]

    def loose_user_columns(self) -> Iterable[Tuple[str, str, Any]]:
        """(table, column, id value) for user_id columns without a foreign key."""
        linked = {(ref.table, ref.column) for refs in self.children.values() for ref in refs}
        for table, cols in self.columns.items():
            for col, info in cols.items():
                if (table, col) in linked or not _LOOSE_USER_COLUMN.match(col):
                    continue
                if isinstance(info["type"], sa.Integer):
                    yield table, col, int
                elif isinstance(info["type"], (sa.String, sa.Text)):
                    yield table, col, str


class _Purge:
    def __init__(self, conn: Connection, schema: _Schema):
        self.conn = conn
        self.schema = schema
        self.deleted: Dict[str, int] = {}
        self.cleared: Dict[str, int] = {}
        self.media: Set[Tuple[str, str]] = set()
        self.firebase_uid: Optional[str] = None

    def _collect_media(self, name: str, cond) -> None:
        cols = self.schema.text_columns(name)
        if not cols:
            return
        t = self.schema.table(name)
        for row in self.conn.execute(sa.select(*(t.c[col] for col in cols)).where(cond)):
            for value in row:
                if value:
                    self.media.update(_MEDIA_URL.findall(str(value)))

    def rows(self, name: str, cond, depth: int = 0, owner_links: bool = False) -> None:
        """Delete the rows of ``name`` matching ``cond`` and everything that needs them."""
        if depth > MAX_DEPTH:
            raise RuntimeError(f"Account deletion found a reference chain deeper than {MAX_DEPTH} at {name}")
        t = self.schema.table(name)
        for ref in self.schema.children.get(name, ()):
            child = self.schema.table(ref.table)
            child_cond = child.c[ref.column].in_(sa.select(t.c[ref.referred]).where(cond))
            keep_row = ref.nullable and not (owner_links and _OWNER_COLUMN.match(ref.column))
            if keep_row:
                result = self.conn.execute(sa.update(child).where(child_cond).values({ref.column: None}))
                if result.rowcount:
                    key = f"{ref.table}.{ref.column}"
                    self.cleared[key] = self.cleared.get(key, 0) + result.rowcount
            else:
                self.rows(ref.table, child_cond, depth + 1)
        self._collect_media(name, cond)
        result = self.conn.execute(sa.delete(t).where(cond))
        if result.rowcount:
            self.deleted[name] = self.deleted.get(name, 0) + result.rowcount


def _purge_user(conn: Connection, user_id: int) -> Optional[_Purge]:
    schema = _Schema(conn)
    if USERS_TABLE not in schema.columns:
        raise RuntimeError("users table not found")
    users = schema.table(USERS_TABLE)
    # Two deletions of one account take turns; the second finds nothing.
    locked = conn.execute(
        sa.select(users).where(users.c.id == user_id).with_for_update()
    ).mappings().first()
    if locked is None:
        return None
    purge = _Purge(conn, schema)
    purge.firebase_uid = locked.get("firebase_uid")
    for table, column, kind in schema.loose_user_columns():
        t = schema.table(table)
        purge.rows(table, t.c[column] == kind(user_id), depth=1)
    purge.rows(USERS_TABLE, users.c.id == user_id, owner_links=True)
    return purge


def _still_referenced(conn: Connection, media: Set[Tuple[str, str]]) -> Set[Tuple[str, str]]:
    """The files in ``media`` that a remaining row still links to."""
    schema = _Schema(conn)
    found: Set[Tuple[str, str]] = set()
    for name in schema.columns:
        t = schema.table(name)
        for col in schema.text_columns(name):
            text = sa.cast(t.c[col], sa.Text)
            for (value,) in conn.execute(sa.select(text).where(text.like("%/api/v1/media/file/%"))):
                if value:
                    found.update(_MEDIA_URL.findall(str(value)))
    return found & media


def _delete_files(media: Iterable[Tuple[str, str]], user_id: int) -> None:
    from lyo_app.routers.clip_media_storage import delete_media
    from lyo_app.routers.user_media import _media_root

    root = _media_root()
    for folder, name in sorted(media):
        try:
            delete_media(folder, name, root)
        except Exception:
            # The account is already gone; the file's random URL is no longer
            # linked from anything. Leave a trace so it can be removed by hand.
            logger.exception("Account %s deleted, but its file %s/%s could not be deleted", user_id, folder, name)


async def _disconnect_sync_devices(user_id: int) -> None:
    """Close this instance's live sync sockets of the user."""
    try:
        from lyo_app.services.conversation_sync import conversation_sync_service as sync
    except Exception:  # noqa: BLE001 — optional module
        return
    devices = sync.connected_devices.pop(user_id, {})
    sync.conversation_states.pop(user_id, None)
    for device in devices.values():
        socket = getattr(device, "websocket", None)
        if socket is None:
            continue
        sync.websocket_to_device.pop(socket, None)
        try:
            await socket.close(code=4001, reason="Account deleted")
        except Exception:  # noqa: BLE001 — already closed
            pass


async def delete_account(db: AsyncSession, user_id: int) -> bool:
    """Delete the account and its personal data. False if it did not exist.

    Database changes commit together or not at all. Stored files and the
    Firebase account are deleted afterwards; a failure there is logged and
    does not bring the account back.
    """
    from starlette.concurrency import run_in_threadpool

    from lyo_app.auth.firebase_auth import firebase_auth_service

    # A copy of the user this session loaded (to authenticate the request)
    # must not be flushed back after its row is gone.
    db.expunge_all()
    try:
        conn = await db.connection()
        purge = await conn.run_sync(_purge_user, user_id)
        if purge is None:
            await db.rollback()
            return False
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "Deleted account %s: rows deleted %s; links cleared %s; files %d",
        user_id, purge.deleted, purge.cleared, len(purge.media),
    )
    media = set(purge.media)
    if media:
        try:
            conn = await db.connection()
            shared = await conn.run_sync(_still_referenced, media)
            await db.rollback()
        except Exception:
            # Without the check a file might be someone else's: keep them all.
            logger.exception("Account %s deleted; could not check which of its files are shared, kept all %d", user_id, len(media))
            await db.rollback()
            shared = media
        if shared:
            logger.info("Account %s deleted; kept %d file(s) other rows still link to", user_id, len(shared))
        media -= shared
    await run_in_threadpool(_delete_files, media, user_id)
    await _disconnect_sync_devices(user_id)
    if purge.firebase_uid:
        await run_in_threadpool(firebase_auth_service.delete_firebase_user, purge.firebase_uid)
    return True
