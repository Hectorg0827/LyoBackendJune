"""Check every clip's video against durable storage and record what was found.

Discover serves only clips whose media_status is "ready". This sets that
status from what storage actually holds:

  ready     the video object exists and is not empty
  missing   the URL is this API's media path but nothing is stored there
            (clips uploaded before durable storage, whose bytes a redeploy
            erased, e.g. legacy clips 1 and 2)
  external  the URL is on another host (anything not in
            DISCOVER_AUDIT_API_HOSTS, default api.lyoai.app), so this API
            cannot vouch for it, even when a file of that name is stored here

It never deletes a clip, never changes who can see it, and never rewrites a
URL. Restoring a missing clip means re-uploading its original file and
publishing it again.

  python scripts/discover_media_audit.py                  # read-only report
  DISCOVER_AUDIT_APPLY=YES \\
  DISCOVER_AUDIT_BACKUP_VERIFIED=YES \\
  DISCOVER_AUDIT_EXPECTED_TARGET=<database host>/<database name> \\
  python scripts/discover_media_audit.py                  # record statuses

Needs the same DATABASE_URL and storage settings as the API it audits.
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg

from lyo_app.models.clips import MEDIA_EXTERNAL, MEDIA_MISSING, MEDIA_READY
from lyo_app.routers.clip_media_storage import media_path_parts, stat_durable_media

# Files on a deployed container's own disk are exactly what a redeploy loses,
# so by default only durable storage counts. Development may point at its
# local upload folder instead.
LOCAL_ROOT = Path(os.getenv("DISCOVER_AUDIT_LOCAL_MEDIA_ROOT", "/nonexistent-local-media"))
# A stored URL keeps whatever host it was saved with. Only hosts that serve
# this API's media can be vouched for; a matching filename elsewhere cannot.
API_HOSTS = {h.strip().lower() for h in os.getenv("DISCOVER_AUDIT_API_HOSTS", "api.lyoai.app").split(",") if h.strip()}


def classify(video_url):
    parts = media_path_parts(video_url)
    host = (urlsplit(video_url or "").hostname or "").lower()
    if not parts or parts[0] != "clips" or (host and host not in API_HOSTS):
        return MEDIA_EXTERNAL, None
    size = stat_durable_media(parts[0], parts[1], LOCAL_ROOT)
    return (MEDIA_READY, size) if size else (MEDIA_MISSING, size)


def database_target(url):
    """'host/database' for a connection URL: the database, not just its server."""
    parts = urlsplit(url)
    return f"{parts.hostname or ''}/{parts.path.lstrip('/')}"


def guard(url):
    apply = os.getenv("DISCOVER_AUDIT_APPLY") == "YES"
    if apply:
        if os.getenv("DISCOVER_AUDIT_BACKUP_VERIFIED") != "YES":
            raise RuntimeError("Verify a database backup before recording statuses")
        if os.getenv("DISCOVER_AUDIT_EXPECTED_TARGET") != database_target(url):
            raise RuntimeError("Confirm the database with DISCOVER_AUDIT_EXPECTED_TARGET=<host>/<database>")
    return apply


async def main():
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
    apply = guard(url)
    connection = await asyncpg.connect(url, timeout=30)
    try:
        # A removed clip's video sits outside the served storage on purpose;
        # auditing it would mark it missing and break its restore.
        rows = await connection.fetch(
            "SELECT id, video_url, media_status, is_public FROM clips "
            "WHERE moderation_status <> 'removed' ORDER BY id"
        )
        findings = []
        for row in rows:
            status, size = await asyncio.to_thread(classify, row["video_url"])
            findings.append({"id": row["id"], "from": row["media_status"], "to": status,
                             "bytes": size, "public": row["is_public"],
                             "video_url": row["video_url"]})
        changed = [f for f in findings if f["from"] != f["to"]]
        updated = 0
        if apply and changed:
            checked_at = datetime.utcnow()
            async with connection.transaction():
                for finding in changed:
                    # Matches the URL and status that were checked, so a clip
                    # edited during the audit is left for the next run.
                    result = await connection.execute(
                        "UPDATE clips SET media_status = $1, media_bytes = $2, media_checked_at = $3 "
                        "WHERE id = $4 AND media_status = $5 AND video_url = $6",
                        finding["to"], finding["bytes"], checked_at, finding["id"], finding["from"],
                        finding["video_url"],
                    )
                    updated += int(result.split()[-1])
        counts = {}
        for finding in findings:
            counts[finding["to"]] = counts.get(finding["to"], 0) + 1
        report = {
            "operation": "discover_media_audit",
            "mode": "apply" if apply else "dry_run",
            "clips": len(findings),
            "statuses": counts,
            "changes": changed,
            "updated_records": updated,
            "preserves": ["clip rows", "visibility", "video URLs", "comments", "likes", "saves"],
        }
        print("DISCOVER_MEDIA_AUDIT=" + json.dumps(report, separators=(",", ":")), flush=True)
        return report
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
