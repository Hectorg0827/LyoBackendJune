"""Regression: Focus's following rail must not silently show the public feed."""

import asyncio
from types import SimpleNamespace

from lyo_app.community.service import CommunityService


class _EmptyResult:
    def fetchall(self):
        return []

    def scalar(self):
        return 0

    def scalars(self):
        return SimpleNamespace(all=lambda: [])


class _RecordingSession:
    def __init__(self):
        self.sql = []

    async def execute(self, query):
        self.sql.append(str(query))
        return _EmptyResult()


def test_following_posts_are_filtered_by_authenticated_users_follows():
    following_db = _RecordingSession()
    recent_db = _RecordingSession()
    service = CommunityService()

    following = asyncio.run(service.get_posts(
        db=following_db, user_id=42, sort_by="following"
    ))
    recent = asyncio.run(service.get_posts(
        db=recent_db, user_id=42, sort_by="recent"
    ))

    assert following["items"] == []
    assert following["total_count"] == 0
    assert recent["items"] == []
    # Second statement counts the filtered post query; page query has the same scope.
    following_sql = " ".join(following_db.sql)
    recent_sql = " ".join(recent_db.sql)
    assert "user_follows" in following_sql
    assert "user_follows.following_id" in following_sql
    assert "user_follows.follower_id" in following_sql
    assert "user_follows" not in recent_sql
