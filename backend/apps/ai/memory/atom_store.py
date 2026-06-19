"""SQLite + FTS5 长期记忆原子存储

参考: astrbot_plugin_livingmemory-master/storage/atom_store.py
适配: 增加 game_id / user_id 字段支持
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite

from apps.ai.memory.atom import AtomStatus, AtomType, MemoryAtom, compute_ttl

import logging

logger = logging.getLogger(__name__)


class AtomStore:
    """SQLite + FTS5 长期记忆原子存储"""

    _SQLITE_BATCH_SIZE = 500

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def _get_db(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(self.db_path)
            await self._db.execute("PRAGMA journal_mode = WAL")
            await self._db.execute("PRAGMA busy_timeout = 10000")
        return self._db

    @asynccontextmanager
    async def _connect(self):
        db = await self._get_db()
        yield db

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    @staticmethod
    def _to_json(payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        return json.dumps(payload if payload is not None else {}, ensure_ascii=False)

    @staticmethod
    def _from_json(payload: str | dict[str, Any] | None) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if not payload:
            return {}
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}

    async def initialize(self) -> None:
        async with self._connect() as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_atoms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_memory_id INTEGER NOT NULL,
                    atom_type TEXT NOT NULL DEFAULT 'unknown',
                    content TEXT NOT NULL,
                    entities TEXT DEFAULT '[]',
                    importance REAL NOT NULL DEFAULT 0.5,
                    confidence REAL NOT NULL DEFAULT 0.7,
                    created_at REAL NOT NULL,
                    last_accessed_at REAL NOT NULL,
                    last_reinforced_at REAL,
                    event_time REAL,
                    ttl_days REAL NOT NULL DEFAULT 30.0,
                    expires_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    reinforcement_count INTEGER NOT NULL DEFAULT 0,
                    decay_type TEXT NOT NULL DEFAULT 'exponential',
                    game_id TEXT,
                    user_id TEXT,
                    session_id TEXT,
                    metadata TEXT DEFAULT '{}'
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_atoms_parent ON memory_atoms(parent_memory_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_atoms_status ON memory_atoms(status)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_atoms_expires ON memory_atoms(expires_at)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_atoms_game_id ON memory_atoms(game_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_atoms_user_id ON memory_atoms(user_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_atoms_type_status ON memory_atoms(atom_type, status)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_atoms_status_expires ON memory_atoms(status, expires_at)"
            )
            await db.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_atoms_fts
                USING fts5(content, atom_id UNINDEXED, tokenize='unicode61')
                """
            )
            await db.commit()
        logger.info(f"AtomStore 初始化完成: {self.db_path}")

    async def insert(self, atom: MemoryAtom) -> int:
        self._prepare_atom_for_insert(atom)
        async with self._connect() as db:
            atom_id = await self._insert_atom(db, atom)
            await db.commit()
        return atom_id

    async def insert_many(self, atoms: list[MemoryAtom]) -> list[int]:
        if not atoms:
            return []
        atom_ids: list[int] = []
        async with self._connect() as db:
            for index in range(0, len(atoms), self._SQLITE_BATCH_SIZE):
                batch = atoms[index : index + self._SQLITE_BATCH_SIZE]
                batch_atom_ids: list[int] = []
                prepared: list[MemoryAtom] = []
                try:
                    for atom in batch:
                        self._prepare_atom_for_insert(atom)
                        prepared.append(atom)
                        batch_atom_ids.append(await self._insert_atom(db, atom))
                    await db.commit()
                except Exception:
                    await db.rollback()
                    for atom in prepared:
                        atom.atom_id = 0
                    raise
                atom_ids.extend(batch_atom_ids)
        return atom_ids

    def _prepare_atom_for_insert(self, atom: MemoryAtom) -> None:
        now = time.time()
        atom.created_at = now
        atom.last_accessed_at = now
        ttl, decay = compute_ttl(
            atom.atom_type, atom.importance, atom.reinforcement_count, atom.event_time
        )
        atom.ttl_days = ttl
        atom.decay_type = decay
        atom.expires_at = now + ttl * 86400.0

    async def _insert_atom(self, db: aiosqlite.Connection, atom: MemoryAtom) -> int:
        cursor = await db.execute(
            """
            INSERT INTO memory_atoms (
                parent_memory_id, atom_type, content, entities,
                importance, confidence, created_at, last_accessed_at,
                last_reinforced_at, event_time, ttl_days, expires_at,
                status, reinforcement_count, decay_type,
                game_id, user_id, session_id, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                atom.parent_memory_id,
                atom.atom_type.value,
                atom.content,
                json.dumps(atom.entities, ensure_ascii=False),
                atom.importance,
                atom.confidence,
                atom.created_at,
                atom.last_accessed_at,
                atom.last_reinforced_at,
                atom.event_time,
                atom.ttl_days,
                atom.expires_at,
                atom.status.value,
                atom.reinforcement_count,
                atom.decay_type.value,
                atom.game_id,
                atom.user_id,
                atom.session_id,
                self._to_json(atom.metadata),
            ),
        )
        atom_id = int(cursor.lastrowid)
        atom.atom_id = atom_id
        await db.execute(
            "INSERT INTO memory_atoms_fts(atom_id, content) VALUES (?, ?)",
            (atom_id, atom.content),
        )
        return atom_id

    async def get(self, atom_id: int) -> MemoryAtom | None:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM memory_atoms WHERE id = ?", (atom_id,)
            )
            row = await cursor.fetchone()
        return self._row_to_atom(row) if row else None

    async def list_atoms(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str = "",
        status: str = "all",
        atom_type: str | None = None,
        game_id: str | None = None,
        user_id: str | None = None,
        sort: str = "created_desc",
    ) -> dict[str, Any]:
        """分页列出记忆原子，供管理/调试页面使用。"""
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 500))
        offset = (page - 1) * page_size

        filters: list[str] = []
        params: list[Any] = []
        if status and status != "all":
            filters.append("status = ?")
            params.append(status)
        if atom_type and atom_type != "all":
            filters.append("atom_type = ?")
            params.append(atom_type)
        if game_id:
            filters.append("game_id = ?")
            params.append(game_id)
        if user_id:
            filters.append("user_id = ?")
            params.append(user_id)
        if keyword:
            keyword_like = f"%{keyword}%"
            if keyword.isdigit():
                filters.append(
                    "(CAST(id AS TEXT) = ? OR content LIKE ? OR entities LIKE ?)"
                )
                params.extend([keyword, keyword_like, keyword_like])
            else:
                filters.append("(content LIKE ? OR entities LIKE ? OR metadata LIKE ?)")
                params.extend([keyword_like, keyword_like, keyword_like])

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        sort_options = {
            "created_desc": "created_at DESC, id DESC",
            "created_asc": "created_at ASC, id ASC",
            "accessed_desc": "last_accessed_at DESC, id DESC",
            "expires_asc": "expires_at ASC, id ASC",
            "importance_desc": "importance DESC, id DESC",
            "importance_asc": "importance ASC, id ASC",
            "type_asc": "atom_type ASC, id DESC",
            "id_desc": "id DESC",
            "id_asc": "id ASC",
        }
        order_by = sort_options.get(sort, sort_options["created_desc"])

        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            count_cursor = await db.execute(
                f"SELECT COUNT(*) AS total FROM memory_atoms {where_clause}",
                params,
            )
            count_row = await count_cursor.fetchone()
            total = int(count_row["total"]) if count_row else 0

            cursor = await db.execute(
                f"""
                SELECT *
                FROM memory_atoms
                {where_clause}
                ORDER BY {order_by}
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, offset),
            )
            rows = await cursor.fetchall()

        return {
            "items": [self._atom_to_dict(self._row_to_atom(row)) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": offset + page_size < total,
        }

    async def get_statistics(self) -> dict[str, Any]:
        """返回记忆原子统计信息。"""
        empty_distribution = {f"{i}-{i + 1}": 0 for i in range(10)}
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            total_row = await (
                await db.execute("SELECT COUNT(*) AS total FROM memory_atoms")
            ).fetchone()
            status_rows = await (
                await db.execute(
                    "SELECT status, COUNT(*) AS count FROM memory_atoms GROUP BY status"
                )
            ).fetchall()
            type_rows = await (
                await db.execute(
                    "SELECT atom_type, COUNT(*) AS count FROM memory_atoms GROUP BY atom_type"
                )
            ).fetchall()
            scope_rows = await (
                await db.execute(
                    """
                    SELECT
                      COUNT(DISTINCT game_id) AS game_count,
                      COUNT(DISTINCT user_id) AS user_count,
                      COUNT(DISTINCT session_id) AS session_count
                    FROM memory_atoms
                    """
                )
            ).fetchone()
            importance_rows = await (
                await db.execute(
                    """
                    SELECT
                      CASE
                        WHEN importance < 0.1 THEN '0-1'
                        WHEN importance < 0.2 THEN '1-2'
                        WHEN importance < 0.3 THEN '2-3'
                        WHEN importance < 0.4 THEN '3-4'
                        WHEN importance < 0.5 THEN '4-5'
                        WHEN importance < 0.6 THEN '5-6'
                        WHEN importance < 0.7 THEN '6-7'
                        WHEN importance < 0.8 THEN '7-8'
                        WHEN importance < 0.9 THEN '8-9'
                        ELSE '9-10'
                      END AS bucket,
                      COUNT(*) AS count
                    FROM memory_atoms
                    GROUP BY bucket
                    """
                )
            ).fetchall()

        distribution = dict(empty_distribution)
        for row in importance_rows:
            distribution[str(row["bucket"])] = int(row["count"])

        return {
            "total_atoms": int(total_row["total"]) if total_row else 0,
            "status_breakdown": {
                str(row["status"]): int(row["count"]) for row in status_rows
            },
            "atom_type_breakdown": {
                str(row["atom_type"]): int(row["count"]) for row in type_rows
            },
            "importance_distribution": distribution,
            "scope": {
                "games": int(scope_rows["game_count"] or 0) if scope_rows else 0,
                "users": int(scope_rows["user_count"] or 0) if scope_rows else 0,
                "sessions": int(scope_rows["session_count"] or 0) if scope_rows else 0,
            },
        }

    async def update_atom_fields(self, atom_id: int, fields: dict[str, Any]) -> MemoryAtom | None:
        """更新管理页面允许编辑的字段，并保持 FTS 同步。"""
        allowed = {
            "content",
            "atom_type",
            "entities",
            "importance",
            "confidence",
            "status",
            "game_id",
            "user_id",
            "session_id",
            "metadata",
        }
        updates: dict[str, Any] = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return await self.get(atom_id)

        if "atom_type" in updates:
            updates["atom_type"] = AtomType(updates["atom_type"]).value
        if "status" in updates:
            updates["status"] = AtomStatus(updates["status"]).value
        if "entities" in updates:
            entities = updates["entities"]
            updates["entities"] = json.dumps(entities if isinstance(entities, list) else [], ensure_ascii=False)
        if "metadata" in updates:
            updates["metadata"] = self._to_json(updates["metadata"])
        for numeric in ("importance", "confidence"):
            if numeric in updates:
                updates[numeric] = max(0.0, min(1.0, float(updates[numeric])))

        assignments = ", ".join(f"{name} = ?" for name in updates)
        values = list(updates.values())
        async with self._connect() as db:
            cursor = await db.execute(
                f"UPDATE memory_atoms SET {assignments} WHERE id = ?",
                (*values, atom_id),
            )
            if cursor.rowcount <= 0:
                await db.rollback()
                return None
            if "content" in updates:
                await db.execute(
                    "DELETE FROM memory_atoms_fts WHERE atom_id = ?",
                    (atom_id,),
                )
                await db.execute(
                    "INSERT INTO memory_atoms_fts(atom_id, content) VALUES (?, ?)",
                    (atom_id, str(fields["content"])),
                )
            await db.commit()
        return await self.get(atom_id)

    async def batch_update_status(self, atom_ids: list[int], status: AtomStatus) -> int:
        if not atom_ids:
            return 0
        placeholders = ",".join("?" * len(atom_ids))
        async with self._connect() as db:
            cursor = await db.execute(
                f"UPDATE memory_atoms SET status = ? WHERE id IN ({placeholders})",
                (status.value, *atom_ids),
            )
            await db.commit()
            return int(cursor.rowcount or 0)

    async def batch_update_fields(self, atom_ids: list[int], fields: dict[str, Any]) -> int:
        if not atom_ids or not fields:
            return 0
        updated = 0
        for atom_id in atom_ids:
            atom = await self.update_atom_fields(atom_id, fields)
            if atom is not None:
                updated += 1
        return updated

    async def search_fts(
        self,
        query: str,
        limit: int = 20,
        game_id: str | None = None,
        user_id: str | None = None,
        atom_types: list[AtomType] | None = None,
        session_id: str | None = None,
        include_expired: bool = False,
    ) -> list[MemoryAtom]:
        """FTS 全文检索 + LIKE 回退，支持 game_id/user_id/atom_types 过滤"""
        filters = ["ma.status = 'active'"] if not include_expired else []
        params: list[Any] = []

        if game_id is not None:
            filters.append("ma.game_id = ?")
            params.append(game_id)
        if user_id is not None:
            filters.append("ma.user_id = ?")
            params.append(user_id)
        if session_id is not None:
            filters.append("ma.session_id = ?")
            params.append(session_id)
        if atom_types:
            placeholders = ",".join("?" * len(atom_types))
            filters.append(f"ma.atom_type IN ({placeholders})")
            params.extend(t.value for t in atom_types)

        where_clause = f"AND {' AND '.join(filters)}" if filters else ""

        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            rows = []

            # FTS 检索
            if query and query.strip():
                tokens = [t for t in query.strip().split() if t]
                if tokens:
                    escaped = [t.replace('"', '""') for t in tokens]
                    fts_tokens = [
                        f'"{t}"' if (" " in t or len(t) > 3) else t
                        for t in escaped
                    ]
                    fts_query = " OR ".join(fts_tokens)
                    fts_params = [fts_query] + params
                    try:
                        cursor = await db.execute(
                            f"""
                            SELECT ma.*, bm25(memory_atoms_fts) AS bm25_score
                            FROM memory_atoms_fts
                            JOIN memory_atoms ma ON ma.id = memory_atoms_fts.atom_id
                            WHERE memory_atoms_fts MATCH ? {where_clause}
                            ORDER BY bm25_score ASC
                            LIMIT ?
                            """,
                            (*fts_params, limit),
                        )
                        rows = await cursor.fetchall()
                    except Exception:
                        rows = []

                    # LIKE 回退
                    if not rows:
                        like_clauses = " OR ".join(
                            ["ma.content LIKE ?" for _ in tokens]
                        )
                        like_params = [f"%{t}%" for t in tokens] + params
                        cursor = await db.execute(
                            f"""
                            SELECT ma.*, 0.5 AS bm25_score
                            FROM memory_atoms ma
                            WHERE ({like_clauses}) {where_clause}
                            ORDER BY ma.id DESC
                            LIMIT ?
                            """,
                            (*like_params, limit),
                        )
                        rows = await cursor.fetchall()
            else:
                # 无查询词，返回所有匹配记录
                cursor = await db.execute(
                    f"""
                    SELECT ma.*, 0.5 AS bm25_score
                    FROM memory_atoms ma
                    WHERE 1=1 {where_clause}
                    ORDER BY ma.importance DESC, ma.created_at DESC
                    LIMIT ?
                    """,
                    (*params, limit),
                )
                rows = await cursor.fetchall()

        if not rows:
            return []

        # 归一化 BM25 分数
        scores = [float(row["bm25_score"]) for row in rows]
        max_score = max(scores)
        min_score = min(scores)
        score_range = max_score - min_score

        atoms: list[MemoryAtom] = []
        now = time.time()
        for row in rows:
            atom = self._row_to_atom(row)
            normalized = (
                1.0
                if score_range == 0
                else (max_score - float(row["bm25_score"])) / score_range
            )
            atom.metadata["bm25_score"] = normalized
            atom.metadata["temporal_score"] = atom.compute_temporal_score(now)
            atoms.append(atom)

        atoms.sort(
            key=lambda a: (
                float(a.metadata.get("bm25_score", 0))
                * float(a.metadata.get("temporal_score", 1))
            ),
            reverse=True,
        )
        return atoms

    async def touch(self, atom_id: int) -> None:
        now = time.time()
        async with self._connect() as db:
            await db.execute(
                "UPDATE memory_atoms SET last_accessed_at = ? WHERE id = ?",
                (now, atom_id),
            )
            await db.commit()

    async def reinforce(
        self, atom_id: int, new_confidence: float | None = None
    ) -> None:
        now = time.time()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT reinforcement_count, importance, confidence, atom_type, event_time FROM memory_atoms WHERE id = ?",
                (atom_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return

            new_count = int(row["reinforcement_count"]) + 1
            importance = float(row["importance"])
            atom_type = AtomType(row["atom_type"])
            event_time = float(row["event_time"]) if row["event_time"] else None
            new_ttl, decay = compute_ttl(atom_type, importance, new_count, event_time)

            confidence = float(row["confidence"])
            if new_confidence is not None:
                confidence = confidence * 0.7 + new_confidence * 0.3

            await db.execute(
                """
                UPDATE memory_atoms
                SET reinforcement_count = ?, confidence = ?,
                    ttl_days = ?, expires_at = ?, decay_type = ?,
                    last_reinforced_at = ?
                WHERE id = ?
                """,
                (
                    new_count,
                    confidence,
                    new_ttl,
                    now + new_ttl * 86400.0,
                    decay.value,
                    now,
                    atom_id,
                ),
            )
            await db.commit()

    async def expire_stale_atoms(self) -> int:
        now = time.time()
        async with self._connect() as db:
            cursor = await db.execute(
                "UPDATE memory_atoms SET status = ? WHERE status = 'active' AND expires_at < ?",
                (AtomStatus.EXPIRED.value, now),
            )
            await db.commit()
            return cursor.rowcount

    async def forget_expired_atoms(self, older_than_days: float = 7.0) -> int:
        cutoff = time.time() - older_than_days * 86400.0
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT id FROM memory_atoms WHERE status = 'expired' AND expires_at < ?",
                (cutoff,),
            )
            rows = await cursor.fetchall()
            atom_ids = [int(row[0]) for row in rows]
            if atom_ids:
                placeholders = ",".join("?" * len(atom_ids))
                await db.execute(
                    f"DELETE FROM memory_atoms_fts WHERE atom_id IN ({placeholders})",
                    atom_ids,
                )
                await db.execute(
                    f"UPDATE memory_atoms SET status = ? WHERE id IN ({placeholders})",
                    (AtomStatus.FORGOTTEN.value, *atom_ids),
                )
                await db.commit()
            return len(atom_ids)

    async def cleanup_forgotten(self, older_than_days: float = 30.0) -> int:
        cutoff = time.time() - older_than_days * 86400.0
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT id FROM memory_atoms WHERE status = 'forgotten' AND expires_at < ?",
                (cutoff,),
            )
            rows = await cursor.fetchall()
            atom_ids = [int(row[0]) for row in rows]
            if atom_ids:
                placeholders = ",".join("?" * len(atom_ids))
                await db.execute(
                    f"DELETE FROM memory_atoms_fts WHERE atom_id IN ({placeholders})",
                    atom_ids,
                )
                await db.execute(
                    f"DELETE FROM memory_atoms WHERE id IN ({placeholders})",
                    atom_ids,
                )
                await db.commit()
            return len(atom_ids)

    def _row_to_atom(self, row: aiosqlite.Row) -> MemoryAtom:
        return MemoryAtom(
            atom_id=int(row["id"]),
            parent_memory_id=int(row["parent_memory_id"]),
            atom_type=AtomType(row["atom_type"]),
            content=str(row["content"]),
            entities=json.loads(row["entities"]) if row["entities"] else [],
            importance=float(row["importance"]),
            confidence=float(row["confidence"]),
            created_at=float(row["created_at"]),
            last_accessed_at=float(row["last_accessed_at"]),
            last_reinforced_at=float(row["last_reinforced_at"]) if row["last_reinforced_at"] else None,
            event_time=float(row["event_time"]) if row["event_time"] else None,
            ttl_days=float(row["ttl_days"]),
            expires_at=float(row["expires_at"]),
            status=AtomStatus(row["status"]),
            reinforcement_count=int(row["reinforcement_count"]),
            decay_type=_parse_decay(row["decay_type"]),
            game_id=str(row["game_id"]) if row["game_id"] else None,
            user_id=str(row["user_id"]) if row["user_id"] else None,
            session_id=str(row["session_id"]) if row["session_id"] else None,
            metadata=self._from_json(row["metadata"]),
        )

    @staticmethod
    def _atom_to_dict(atom: MemoryAtom) -> dict[str, Any]:
        return {
            "id": atom.atom_id,
            "parent_memory_id": atom.parent_memory_id,
            "atom_type": atom.atom_type.value,
            "content": atom.content,
            "entities": atom.entities,
            "importance": atom.importance,
            "confidence": atom.confidence,
            "created_at": atom.created_at,
            "last_accessed_at": atom.last_accessed_at,
            "last_reinforced_at": atom.last_reinforced_at,
            "event_time": atom.event_time,
            "ttl_days": atom.ttl_days,
            "expires_at": atom.expires_at,
            "status": atom.status.value,
            "reinforcement_count": atom.reinforcement_count,
            "decay_type": atom.decay_type.value,
            "game_id": atom.game_id,
            "user_id": atom.user_id,
            "session_id": atom.session_id,
            "metadata": atom.metadata,
        }


def _parse_decay(value: str) -> "DecayType":
    from apps.ai.memory.atom import DecayType
    try:
        return DecayType(value)
    except ValueError:
        return DecayType.EXPONENTIAL


__all__ = ["AtomStore"]
