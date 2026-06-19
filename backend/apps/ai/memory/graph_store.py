"""游戏知识图谱 — 按游戏ID独立存储

节点类型: card / relic / enemy / event / mechanic
边类型: synergizes_with / counters / belongs_to / found_in

构建: MCP Adapter 从游戏状态中提取
读取: 查询协同/克制关系，注入到 GameGraph prompt
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite

import logging

logger = logging.getLogger(__name__)


class GameKnowledgeGraph:
    """游戏知识图谱 — 按游戏ID独立存储"""

    def __init__(self, db_path: str, game_id: str):
        self._db_path = db_path
        self._game_id = game_id
        self._db: aiosqlite.Connection | None = None

    @property
    def game_id(self) -> str:
        return self._game_id

    async def _get_db(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(self._db_path)
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

    async def initialize(self) -> None:
        async with self._connect() as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    canonical_name TEXT NOT NULL,
                    properties TEXT DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(game_id, canonical_name)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL,
                    source_id INTEGER NOT NULL REFERENCES graph_nodes(id),
                    target_id INTEGER NOT NULL REFERENCES graph_nodes(id),
                    relation TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.7,
                    evidence TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    UNIQUE(source_id, target_id, relation)
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_nodes_game ON graph_nodes(game_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_nodes_type ON graph_nodes(game_id, node_type)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_edges_game ON graph_edges(game_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(source_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target_id)"
            )
            await db.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS graph_nodes_fts
                USING fts5(name, properties, node_id UNINDEXED, tokenize='unicode61')
                """
            )
            await db.commit()
        logger.info(f"知识图谱初始化完成: game={self._game_id}")

    async def add_node(self, node_type: str, name: str, properties: dict | None = None) -> int:
        """添加节点，已存在则更新 properties。返回节点 ID"""
        canonical = self._canonicalize(name)
        props_json = json.dumps(properties or {}, ensure_ascii=False)
        now = time.time()

        async with self._connect() as db:
            # 尝试更新已有节点
            cursor = await db.execute(
                """
                UPDATE graph_nodes
                SET properties = ?, updated_at = ?
                WHERE game_id = ? AND canonical_name = ?
                """,
                (props_json, now, self._game_id, canonical),
            )
            if cursor.rowcount > 0:
                cursor = await db.execute(
                    "SELECT id FROM graph_nodes WHERE game_id = ? AND canonical_name = ?",
                    (self._game_id, canonical),
                )
                row = await cursor.fetchone()
                await db.commit()
                return int(row[0])

            # 新建节点
            cursor = await db.execute(
                """
                INSERT INTO graph_nodes (game_id, node_type, name, canonical_name, properties, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (self._game_id, node_type, name, canonical, props_json, now, now),
            )
            node_id = int(cursor.lastrowid)
            await db.execute(
                "INSERT INTO graph_nodes_fts(node_id, name, properties) VALUES (?, ?, ?)",
                (node_id, name, props_json),
            )
            await db.commit()
            logger.debug(f"知识图谱新增节点: [{node_type}] {name}")
            return node_id

    async def add_edge(
        self,
        source_id: int,
        target_id: int,
        relation: str,
        confidence: float = 0.7,
        evidence: str = "",
    ) -> None:
        """添加边，已存在则更新 confidence"""
        now = time.time()
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO graph_edges (game_id, source_id, target_id, relation, confidence, evidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, relation) DO UPDATE SET
                    confidence = MAX(confidence, excluded.confidence),
                    evidence = CASE WHEN excluded.evidence != '' THEN excluded.evidence ELSE evidence END
                """,
                (self._game_id, source_id, target_id, relation, confidence, evidence, now),
            )
            await db.commit()

    async def add_edge_by_name(
        self,
        source_name: str,
        target_name: str,
        relation: str,
        confidence: float = 0.7,
        evidence: str = "",
    ) -> bool:
        """通过节点名称添加边，任一节点不存在则返回 False"""
        source_id = await self._get_node_id(source_name)
        target_id = await self._get_node_id(target_name)
        if source_id is None or target_id is None:
            return False
        await self.add_edge(source_id, target_id, relation, confidence, evidence)
        return True

    async def get_synergies(self, node_name: str) -> list[dict]:
        """获取与某个节点协同的其他节点"""
        node_id = await self._get_node_id(node_name)
        if node_id is None:
            return []
        return await self._get_related_nodes(node_id, "synergizes_with")

    async def get_countered_by(self, enemy_name: str) -> list[dict]:
        """获取克制某个敌人的卡牌/遗物 (反向查询 counters 边)"""
        node_id = await self._get_node_id(enemy_name)
        if node_id is None:
            return []
        return await self._get_reverse_related(node_id, "counters")

    async def get_related(self, node_names: list[str]) -> str:
        """根据一组节点名称，生成知识图谱上下文文本"""
        if not node_names:
            return ""

        sections: list[str] = []
        for name in node_names:
            synergies = await self.get_synergies(name)
            if synergies:
                items = [f"  - {s['name']} ({s['node_type']})" for s in synergies]
                sections.append(f"与【{name}】协同:\n" + "\n".join(items))

            counters = await self.get_countered_by(name)
            if counters:
                items = [f"  - {c['name']} ({c['node_type']})" for c in counters]
                sections.append(f"克制【{name}】:\n" + "\n".join(items))

        return "\n\n".join(sections) if sections else ""

    async def search(self, query: str, k: int = 5) -> list[dict]:
        """检索相关知识节点"""
        if not query or not query.strip():
            return []

        tokens = [t for t in query.strip().split() if t]
        if not tokens:
            return []
        escaped = [t.replace('"', '""') for t in tokens]
        fts_tokens = [f'"{t}"' if " " in t or len(t) > 3 else t for t in escaped]
        fts_query = " OR ".join(fts_tokens)

        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            try:
                cursor = await db.execute(
                    """
                    SELECT gn.*, bm25(graph_nodes_fts) AS bm25_score
                    FROM graph_nodes_fts
                    JOIN graph_nodes gn ON gn.id = graph_nodes_fts.node_id
                    WHERE graph_nodes_fts MATCH ? AND gn.game_id = ?
                    ORDER BY bm25_score ASC
                    LIMIT ?
                    """,
                    (fts_query, self._game_id, k),
                )
                rows = await cursor.fetchall()
            except Exception:
                rows = []

            if not rows:
                like_clauses = " OR ".join(["gn.name LIKE ?" for _ in tokens])
                like_params = [f"%{t}%" for t in tokens] + [self._game_id]
                cursor = await db.execute(
                    f"""
                    SELECT gn.*, 0.5 AS bm25_score
                    FROM graph_nodes gn
                    WHERE ({like_clauses}) AND gn.game_id = ?
                    LIMIT ?
                    """,
                    (*like_params, k),
                )
                rows = await cursor.fetchall()

        return [self._row_to_node_dict(row) for row in rows]

    async def ingest(self, knowledge_items: list[dict]) -> int:
        """批量导入知识 (节点+边)

        每个 item 格式:
        - {"type": "node", "node_type": "card", "name": "旋风斩", "properties": {...}}
        - {"type": "edge", "source": "旋风斩", "target": "双发", "relation": "synergizes_with", "evidence": "..."}
        """
        count = 0
        for item in knowledge_items:
            try:
                if item.get("type") == "node":
                    await self.add_node(
                        node_type=item["node_type"],
                        name=item["name"],
                        properties=item.get("properties"),
                    )
                    count += 1
                elif item.get("type") == "edge":
                    ok = await self.add_edge_by_name(
                        source_name=item["source"],
                        target_name=item["target"],
                        relation=item["relation"],
                        confidence=item.get("confidence", 0.7),
                        evidence=item.get("evidence", ""),
                    )
                    if ok:
                        count += 1
            except Exception as e:
                logger.warning(f"知识导入失败: {item} -> {e}")
        return count

    async def _get_node_id(self, name: str) -> int | None:
        canonical = self._canonicalize(name)
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT id FROM graph_nodes WHERE game_id = ? AND canonical_name = ?",
                (self._game_id, canonical),
            )
            row = await cursor.fetchone()
            return int(row[0]) if row else None

    async def _get_related_nodes(self, node_id: int, relation: str) -> list[dict]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT gn.*, ge.confidence, ge.evidence
                FROM graph_edges ge
                JOIN graph_nodes gn ON gn.id = ge.target_id
                WHERE ge.source_id = ? AND ge.relation = ? AND ge.game_id = ?
                ORDER BY ge.confidence DESC
                """,
                (node_id, relation, self._game_id),
            )
            rows = await cursor.fetchall()
        return [self._row_to_node_dict(row) for row in rows]

    async def _get_reverse_related(self, node_id: int, relation: str) -> list[dict]:
        """反向查询: 查找指向当前节点的边"""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT gn.*, ge.confidence, ge.evidence
                FROM graph_edges ge
                JOIN graph_nodes gn ON gn.id = ge.source_id
                WHERE ge.target_id = ? AND ge.relation = ? AND ge.game_id = ?
                ORDER BY ge.confidence DESC
                """,
                (node_id, relation, self._game_id),
            )
            rows = await cursor.fetchall()
        return [self._row_to_node_dict(row) for row in rows]

    @staticmethod
    def _canonicalize(name: str) -> str:
        """规范化节点名称 (去空格、小写)"""
        return name.strip().lower().replace(" ", "")

    @staticmethod
    def _row_to_node_dict(row: aiosqlite.Row) -> dict:
        result = {
            "id": int(row["id"]),
            "node_type": str(row["node_type"]),
            "name": str(row["name"]),
            "properties": json.loads(row["properties"]) if row["properties"] else {},
        }
        if "confidence" in row.keys():
            result["confidence"] = float(row["confidence"])
        if "evidence" in row.keys():
            result["evidence"] = str(row["evidence"])
        return result


__all__ = ["GameKnowledgeGraph"]
