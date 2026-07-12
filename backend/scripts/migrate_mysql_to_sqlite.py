"""One-time MySQL to SQLite import.

Install the optional dependency first:
    uv sync --extra mysql-migration

Then provide the old URL without putting credentials in source control:
    $env:MYSQL_SOURCE_URL='mysql+aiomysql://...'
    uv run python scripts/migrate_mysql_to_sqlite.py
"""

from __future__ import annotations

import asyncio
import json
import os
import time

import aiomysql
from sqlalchemy.engine import make_url

from apps.ai.memory.atom import AtomType, MemoryAtom
from apps.ai.memory.atom_store import AtomStore
from apps.config import config
from apps.db import init_db


async def _fetch_table(cursor, table: str) -> list[dict]:
    await cursor.execute(f"SELECT * FROM `{table}`")
    return list(await cursor.fetchall())


async def migrate() -> None:
    source = os.getenv("MYSQL_SOURCE_URL", "")
    if not source:
        raise SystemExit("MYSQL_SOURCE_URL is required")
    url = make_url(source)
    connection = await aiomysql.connect(
        host=url.host or "localhost",
        port=url.port or 3306,
        user=url.username,
        password=url.password,
        db=url.database,
        cursorclass=aiomysql.DictCursor,
    )
    try:
        async with connection.cursor() as cursor:
            profiles = await _fetch_table(cursor, "user_profiles")
            videos = await _fetch_table(cursor, "up_videos")
            playlist = await _fetch_table(cursor, "playlist")
    finally:
        connection.close()

    await init_db()
    import aiosqlite

    async with aiosqlite.connect(config.app_db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        for row in profiles:
            await db.execute(
                """
                INSERT OR REPLACE INTO viewer_profiles(
                    user_id,username,danmaku_count,interaction_count,key_topics,
                    impression,last_danmaku,last_interaction,last_summary_count,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(row["user_id"]), row.get("username", ""),
                    row.get("danmaku_count", 0), row.get("interaction_count", 0),
                    row.get("key_topics", "[]"), row.get("impression", ""),
                    row.get("last_danmaku", ""), float(row.get("last_interaction", 0)),
                    row.get("last_summary_count", 0), float(row.get("created_at", 0)),
                ),
            )
            for turn in json.loads(row.get("recent_messages") or "[]"):
                await db.execute(
                    "INSERT INTO viewer_interactions(user_id,role,content,created_at) VALUES(?,?,?,?)",
                    (str(row["user_id"]), turn.get("role", "user"), turn.get("content", ""), time.time()),
                )
        for row in videos:
            await db.execute(
                """
                INSERT OR REPLACE INTO up_video_cache(
                    id,bvid,title,up_name,up_uid,duration,cover_url,fetched_at,last_seen_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (row["id"], row["bvid"], row["title"], row["up_name"], row["up_uid"], row.get("duration", 0), row.get("cover_url", ""), row.get("fetched_at"), row.get("fetched_at")),
            )
        for row in playlist:
            await db.execute(
                "INSERT OR REPLACE INTO playlist_items(id,bvid,title,artist,enabled,created_at) VALUES(?,?,?,?,?,?)",
                (row["id"], row["bvid"], row["title"], row.get("artist", ""), row.get("enabled", True), row.get("created_at")),
            )
        await db.commit()

    store = AtomStore(config.app_db_path)
    await store.initialize()
    try:
        for row in profiles:
            fact = str(row.get("long_term_memory") or "").strip()
            if fact:
                await store.insert(
                    MemoryAtom(
                        atom_type=AtomType.VIEWER_FACT,
                        content=fact,
                        entities=[str(row.get("username") or row["user_id"])],
                        user_id=str(row["user_id"]),
                        importance=0.75,
                        metadata={"source": "mysql_user_profiles"},
                    )
                )
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(migrate())
