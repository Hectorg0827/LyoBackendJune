"""Safely quarantine two confirmed missing Discover clips; no deletes.

Run with a *production* DATABASE_URL only after a database snapshot:
  python scripts/quarantine_missing_discover_media.py                 # read-only plan
  DISCOVER_QUARANTINE_APPLY=YES python scripts/quarantine_missing_discover_media.py

Matches both id and exact expected video_url path. Refuses ambiguous data.
Restoration requires an independently verified backup or asset, then an audited
manual UPDATE; this command never automatically republishes missing media.
"""
import asyncio
import json
import os
from urllib.parse import urlsplit

import asyncpg

EXPECTED = {
    1: "/api/v1/media/file/clips/59723341c48f4e92ba025fdae0904bbf.mp4",
    2: "/api/v1/media/file/clips/d8fd2b0b576e42a7ad61f308fc6751d6.mp4",
}

async def main():
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
    apply = os.getenv("DISCOVER_QUARANTINE_APPLY") == "YES"
    if apply:
        if os.getenv("DISCOVER_QUARANTINE_CONFIRM_IDS") != "1,2":
            raise RuntimeError("Expected clip IDs must be explicitly confirmed")
        if os.getenv("DISCOVER_QUARANTINE_BACKUP_VERIFIED") != "YES":
            raise RuntimeError("Database backup must be verified before writes")
        if os.getenv("DISCOVER_QUARANTINE_EXPECTED_HOST") != (urlsplit(url).hostname or ""):
            raise RuntimeError("Database host must be explicitly confirmed")
    connection = await asyncpg.connect(url)
    try:
        async with connection.transaction(readonly=not apply):
            rows = await connection.fetch(
                "SELECT id, video_url, is_public FROM clips WHERE id = ANY($1::integer[]) ORDER BY id FOR UPDATE"
                if apply else
                "SELECT id, video_url, is_public FROM clips WHERE id = ANY($1::integer[]) ORDER BY id",
                list(EXPECTED),
            )
            if len(rows) != len(EXPECTED):
                raise RuntimeError("Unexpected clip count; refusing changes")
            for row in rows:
                path = urlsplit(row["video_url"] or "").path
                if path != EXPECTED[row["id"]]:
                    raise RuntimeError(f"Clip {row['id']} changed URL; refusing changes")
            original = [{"id": r["id"], "video_url": r["video_url"], "is_public": r["is_public"]} for r in rows]
            affected = 0
            if apply:
                for row in rows:
                    if row["is_public"]:
                        result = await connection.execute(
                            "UPDATE clips SET is_public = FALSE, updated_at = NOW() "
                            "WHERE id = $1 AND video_url = $2 AND is_public IS TRUE",
                            row["id"], row["video_url"],
                        )
                        if result != "UPDATE 1":
                            raise RuntimeError("Concurrent clip change; rolling back")
                        affected += 1
            report = {"operation": "quarantine_confirmed_missing_media", "mode": "apply" if apply else "dry_run",
                      "original": original, "updated_records": affected,
                      "preserves": ["clip rows", "user ownership", "comments", "saves"],
                      "postcondition": "confirmed missing media hidden from public Discover"}
            print("DISCOVER_QUARANTINE_AUDIT=" + json.dumps(report, separators=(",", ":")), flush=True)
    finally:
        await connection.close()

if __name__ == "__main__":
    asyncio.run(main())
