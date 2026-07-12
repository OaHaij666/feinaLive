"""Small, explicit SQLite migrations for tables not managed by SQLAlchemy.

FTS5 and the memory graph use SQLite-specific DDL, so keeping the schema
version beside the database is more reliable than hiding those changes behind
``create_all``.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 3


def _copy_legacy_memory_database(target: Path) -> None:
    legacy = target.with_name("memory.db")
    if target.exists() or not legacy.exists() or legacy.resolve() == target.resolve():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    source_db = sqlite3.connect(str(legacy))
    target_db = sqlite3.connect(str(target))
    try:
        source_db.backup(target_db)
        target_db.commit()
        logger.info("Imported legacy memory database into %s", target)
    finally:
        target_db.close()
        source_db.close()


def prepare_database(db_path: str) -> None:
    """Create the database location and apply idempotent bootstrap migrations."""

    path = Path(db_path).resolve()
    _copy_legacy_memory_database(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    try:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        profile_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='viewer_profiles'"
        ).fetchone()
        if profile_table:
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(viewer_profiles)").fetchall()
            }
            if "last_summarized_interaction_id" not in columns:
                connection.execute(
                    "ALTER TABLE viewer_profiles "
                    "ADD COLUMN last_summarized_interaction_id INTEGER NOT NULL DEFAULT 0"
                )
        connection.execute("DROP TABLE IF EXISTS app_settings")
        connection.commit()
    finally:
        connection.close()
