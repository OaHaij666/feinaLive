"""Unified user/game knowledge graph backed by SQLite."""

from __future__ import annotations

import json
import math
import time
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite

from apps.ai.memory.atom import MemoryAtom, compute_decay_score


async def initialize_knowledge_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_type TEXT NOT NULL CHECK(owner_type IN ('user','game','global')),
            owner_id TEXT NOT NULL DEFAULT '',
            node_type TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            label TEXT NOT NULL,
            properties TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'active',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(owner_type, owner_id, node_type, canonical_key)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_node_id INTEGER NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
            target_node_id INTEGER NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
            relation TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.7,
            effective_strength REAL NOT NULL DEFAULT 0.7,
            status TEXT NOT NULL DEFAULT 'active',
            first_observed_at REAL NOT NULL,
            last_confirmed_at REAL NOT NULL,
            UNIQUE(source_node_id, target_node_id, relation)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_edge_evidence (
            edge_id INTEGER NOT NULL REFERENCES knowledge_edges(id) ON DELETE CASCADE,
            atom_id INTEGER NOT NULL REFERENCES memory_atoms(id) ON DELETE CASCADE,
            stance TEXT NOT NULL DEFAULT 'supports' CHECK(stance IN ('supports','contradicts')),
            evidence_weight REAL NOT NULL DEFAULT 1.0,
            created_at REAL NOT NULL,
            PRIMARY KEY(edge_id, atom_id, stance)
        )
        """
    )
    await db.execute("CREATE INDEX IF NOT EXISTS idx_kn_owner ON knowledge_nodes(owner_type, owner_id, status)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_ke_source ON knowledge_edges(source_node_id, status)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_ke_target ON knowledge_edges(target_node_id, status)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_kee_atom ON knowledge_edge_evidence(atom_id)")
    await db.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_nodes_fts
        USING fts5(label, properties, node_id UNINDEXED, tokenize='unicode61')
        """
    )
    legacy = await (
        await db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='graph_nodes'"
        )
    ).fetchone()
    if legacy:
        db.row_factory = aiosqlite.Row
        node_map: dict[int, int] = {}
        rows = await (await db.execute("SELECT * FROM graph_nodes ORDER BY id")).fetchall()
        for row in rows:
            node_map[int(row["id"])] = await _upsert_node(
                db,
                owner_type="game",
                owner_id=str(row["game_id"]),
                node_type=str(row["node_type"]),
                canonical_key=str(row["canonical_name"]),
                label=str(row["name"]),
                properties=json.loads(row["properties"] or "{}"),
            )
        edge_rows = await (await db.execute("SELECT * FROM graph_edges ORDER BY id")).fetchall()
        for row in edge_rows:
            source = node_map.get(int(row["source_id"]))
            target = node_map.get(int(row["target_id"]))
            if source and target:
                await _upsert_edge(
                    db,
                    source,
                    target,
                    str(row["relation"]),
                    confidence=float(row["confidence"]),
                )
        await db.execute("DROP TABLE IF EXISTS graph_nodes_fts")
        await db.execute("DROP TABLE IF EXISTS graph_edges")
        await db.execute("DROP TABLE IF EXISTS graph_nodes")


def _scope_for_atom(atom: MemoryAtom) -> tuple[str, str]:
    if atom.user_id:
        return "user", str(atom.user_id)
    if atom.game_id:
        return "game", str(atom.game_id)
    return "global", ""


async def _upsert_node(
    db: aiosqlite.Connection,
    *,
    owner_type: str,
    owner_id: str,
    node_type: str,
    canonical_key: str,
    label: str,
    properties: dict[str, Any] | None = None,
) -> int:
    now = time.time()
    payload = json.dumps(properties or {}, ensure_ascii=False)
    await db.execute(
        """
        INSERT INTO knowledge_nodes(
            owner_type, owner_id, node_type, canonical_key, label,
            properties, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(owner_type, owner_id, node_type, canonical_key) DO UPDATE SET
            label=excluded.label, properties=excluded.properties,
            updated_at=excluded.updated_at, status='active'
        """,
        (owner_type, owner_id, node_type, canonical_key, label, payload, now, now),
    )
    row = await (
        await db.execute(
            """
            SELECT id FROM knowledge_nodes
            WHERE owner_type=? AND owner_id=? AND node_type=? AND canonical_key=?
            """,
            (owner_type, owner_id, node_type, canonical_key),
        )
    ).fetchone()
    node_id = int(row[0])
    await db.execute("DELETE FROM knowledge_nodes_fts WHERE node_id=?", (node_id,))
    await db.execute(
        "INSERT INTO knowledge_nodes_fts(node_id,label,properties) VALUES(?,?,?)",
        (node_id, label, payload),
    )
    return node_id


async def _upsert_edge(
    db: aiosqlite.Connection,
    source_node_id: int,
    target_node_id: int,
    relation: str,
    *,
    confidence: float = 0.7,
    evidence_atom_id: int | None = None,
    stance: str = "supports",
) -> int:
    now = time.time()
    await db.execute(
        """
        INSERT INTO knowledge_edges(
            source_node_id,target_node_id,relation,confidence,effective_strength,
            first_observed_at,last_confirmed_at
        ) VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(source_node_id,target_node_id,relation) DO UPDATE SET
            confidence=MAX(confidence,excluded.confidence),
            last_confirmed_at=excluded.last_confirmed_at,
            status='active'
        """,
        (source_node_id, target_node_id, relation, confidence, confidence, now, now),
    )
    edge_id = int(
        (
            await (
                await db.execute(
                    "SELECT id FROM knowledge_edges WHERE source_node_id=? AND target_node_id=? AND relation=?",
                    (source_node_id, target_node_id, relation),
                )
            ).fetchone()
        )[0]
    )
    if evidence_atom_id:
        await db.execute(
            """
            INSERT OR REPLACE INTO knowledge_edge_evidence(
                edge_id,atom_id,stance,evidence_weight,created_at
            ) VALUES(?,?,?,?,?)
            """,
            (edge_id, evidence_atom_id, stance, 1.0, now),
        )
    return edge_id


async def attach_atom_to_graph(
    db: aiosqlite.Connection, atom_id: int, atom: MemoryAtom
) -> int:
    """Create the atom node, owner link, entities and normalized relations."""

    owner_type, owner_id = _scope_for_atom(atom)
    atom_node_id = await _upsert_node(
        db,
        owner_type=owner_type,
        owner_id=owner_id,
        node_type="memory_atom",
        canonical_key=f"atom:{atom_id}",
        label=atom.content[:160],
        properties={"atom_id": atom_id, "atom_type": atom.atom_type.value},
    )
    previous_edges = [
        int(row[0])
        for row in await (
            await db.execute(
                "SELECT edge_id FROM knowledge_edge_evidence WHERE atom_id=?",
                (atom_id,),
            )
        ).fetchall()
    ]
    await db.execute(
        "DELETE FROM knowledge_edge_evidence WHERE atom_id=?", (atom_id,)
    )
    for edge_id in previous_edges:
        await db.execute(
            """
            DELETE FROM knowledge_edges
            WHERE id=? AND NOT EXISTS(
                SELECT 1 FROM knowledge_edge_evidence WHERE edge_id=?
            )
            """,
            (edge_id, edge_id),
        )
    await db.execute(
        "DELETE FROM knowledge_edges WHERE source_node_id=? AND relation='mentions'",
        (atom_node_id,),
    )
    await db.execute("UPDATE memory_atoms SET node_id=? WHERE id=?", (atom_node_id, atom_id))

    owner_node_id: int | None = None
    if owner_type == "user":
        owner_node_id = await _upsert_node(
            db,
            owner_type=owner_type,
            owner_id=owner_id,
            node_type="user",
            canonical_key=f"user:{owner_id}",
            label=owner_id,
        )
    elif owner_type == "game":
        owner_node_id = await _upsert_node(
            db,
            owner_type=owner_type,
            owner_id=owner_id,
            node_type="game",
            canonical_key=f"game:{owner_id}",
            label=owner_id,
        )
    if owner_node_id:
        await _upsert_edge(
            db, owner_node_id, atom_node_id, "remembers", evidence_atom_id=atom_id
        )

    entity_nodes: dict[str, int] = {}
    for entity in atom.entities:
        label = str(entity).strip()
        if not label:
            continue
        canonical = label.lower().replace(" ", "")
        entity_nodes[canonical] = await _upsert_node(
            db,
            owner_type=owner_type,
            owner_id=owner_id,
            node_type="entity",
            canonical_key=canonical,
            label=label,
        )
        await _upsert_edge(
            db,
            atom_node_id,
            entity_nodes[canonical],
            "mentions",
            confidence=atom.confidence,
            evidence_atom_id=atom_id,
        )

    for relation in atom.metadata.get("relations", []):
        if not isinstance(relation, dict):
            continue
        subject = str(relation.get("subject", "")).strip()
        predicate = str(relation.get("predicate", "related_to")).strip()
        obj = str(relation.get("object", "")).strip()
        if not subject or not obj or not predicate:
            continue

        async def relation_node(label: str) -> int:
            if owner_node_id and label.lower() in {"user", "用户", owner_id.lower()}:
                return owner_node_id
            canonical = label.lower().replace(" ", "")
            return await _upsert_node(
                db,
                owner_type=owner_type,
                owner_id=owner_id,
                node_type="entity",
                canonical_key=canonical,
                label=label,
            )

        await _upsert_edge(
            db,
            await relation_node(subject),
            await relation_node(obj),
            predicate,
            confidence=atom.confidence,
            evidence_atom_id=atom_id,
            stance=str(relation.get("stance", "supports")),
        )
    return atom_node_id


async def expand_graph_from_atoms(
    db_path: str,
    owner_type: str,
    owner_id: str,
    atom_ids: list[int],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Expand owner-scoped facts around entities mentioned by seed atoms."""

    if owner_type not in {"user", "game"} or not atom_ids:
        return []
    placeholders = ",".join("?" * len(atom_ids))
    structural_relations = ("remembers", "mentions")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        rows = await (
            await db.execute(
                f"""
                WITH seed_entities(id) AS (
                    SELECT DISTINCT edge.target_node_id
                    FROM knowledge_edges edge
                    JOIN memory_atoms atom ON atom.node_id=edge.source_node_id
                    JOIN knowledge_nodes entity ON entity.id=edge.target_node_id
                    WHERE atom.id IN ({placeholders})
                      AND edge.relation='mentions'
                      AND entity.node_type='entity'
                    UNION
                    SELECT DISTINCT node.id
                    FROM knowledge_edge_evidence evidence
                    JOIN knowledge_edges edge ON edge.id=evidence.edge_id
                    JOIN knowledge_nodes node
                      ON node.id IN (edge.source_node_id, edge.target_node_id)
                    WHERE evidence.atom_id IN ({placeholders})
                      AND edge.relation NOT IN (?, ?)
                      AND node.node_type='entity'
                )
                SELECT edge.id, edge.relation, edge.confidence,
                       edge.effective_strength,
                       source.label AS source_label,
                       source.node_type AS source_type,
                       target.label AS target_label,
                       target.node_type AS target_type
                FROM knowledge_edges edge
                JOIN knowledge_nodes source ON source.id=edge.source_node_id
                JOIN knowledge_nodes target ON target.id=edge.target_node_id
                WHERE edge.status='active'
                  AND edge.relation NOT IN (?, ?)
                  AND source.owner_type=? AND source.owner_id=?
                  AND target.owner_type=? AND target.owner_id=?
                  AND (
                    edge.source_node_id IN (SELECT id FROM seed_entities)
                    OR edge.target_node_id IN (SELECT id FROM seed_entities)
                  )
                ORDER BY edge.effective_strength DESC, edge.confidence DESC
                LIMIT ?
                """,
                (
                    *atom_ids,
                    *atom_ids,
                    *structural_relations,
                    *structural_relations,
                    owner_type,
                    owner_id,
                    owner_type,
                    owner_id,
                    limit,
                ),
            )
        ).fetchall()
    return [dict(row) for row in rows]


async def expand_user_graph_from_atoms(
    db_path: str,
    user_id: str,
    atom_ids: list[int],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    return await expand_graph_from_atoms(
        db_path, "user", user_id, atom_ids, limit=limit
    )


class GameKnowledgeGraph:
    """Compatibility wrapper over the unified graph for one game owner."""

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
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA busy_timeout=10000")
            await self._db.execute("PRAGMA foreign_keys=ON")
        return self._db

    @asynccontextmanager
    async def _connect(self):
        yield await self._get_db()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def initialize(self) -> None:
        async with self._connect() as db:
            await initialize_knowledge_schema(db)
            await db.commit()

    async def add_node(self, node_type: str, name: str, properties: dict | None = None) -> int:
        async with self._connect() as db:
            node_id = await _upsert_node(
                db,
                owner_type="game",
                owner_id=self._game_id,
                node_type=node_type,
                canonical_key=self._canonicalize(name),
                label=name,
                properties=properties,
            )
            await db.commit()
            return node_id

    async def add_edge(self, source_id: int, target_id: int, relation: str, confidence: float = 0.7, evidence: str = "") -> None:
        async with self._connect() as db:
            await _upsert_edge(db, source_id, target_id, relation, confidence=confidence)
            await db.commit()

    async def add_edge_by_name(self, source_name: str, target_name: str, relation: str, confidence: float = 0.7, evidence: str = "") -> bool:
        source_id = await self._get_node_id(source_name)
        target_id = await self._get_node_id(target_name)
        if source_id is None or target_id is None:
            return False
        await self.add_edge(source_id, target_id, relation, confidence, evidence)
        return True

    async def get_synergies(self, node_name: str) -> list[dict]:
        node_id = await self._get_node_id(node_name)
        return [] if node_id is None else await self._related(node_id, "synergizes_with", False)

    async def get_countered_by(self, node_name: str) -> list[dict]:
        node_id = await self._get_node_id(node_name)
        return [] if node_id is None else await self._related(node_id, "counters", True)

    async def get_related(self, node_names: list[str]) -> str:
        sections: list[str] = []
        for name in node_names:
            related = await self.get_synergies(name)
            if related:
                sections.append(f"与【{name}】协同：" + "、".join(item["name"] for item in related))
            counters = await self.get_countered_by(name)
            if counters:
                sections.append(f"克制【{name}】：" + "、".join(item["name"] for item in counters))
        return "\n".join(sections)

    async def search(self, query: str, k: int = 5) -> list[dict]:
        if not query.strip():
            return []
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(
                    """
                    SELECT * FROM knowledge_nodes
                    WHERE owner_type='game' AND owner_id=? AND status='active'
                      AND (label LIKE ? OR properties LIKE ?)
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (self._game_id, f"%{query}%", f"%{query}%", k),
                )
            ).fetchall()
        return [self._node_dict(row) for row in rows]

    async def ingest(self, knowledge_items: list[dict]) -> int:
        count = 0
        for item in knowledge_items:
            if item.get("type") == "node":
                await self.add_node(item["node_type"], item["name"], item.get("properties"))
                count += 1
            elif item.get("type") == "edge" and await self.add_edge_by_name(
                item["source"], item["target"], item["relation"], item.get("confidence", 0.7), item.get("evidence", "")
            ):
                count += 1
        return count

    async def get_all_node_names(self) -> list[str]:
        async with self._connect() as db:
            rows = await (await db.execute(
                "SELECT label FROM knowledge_nodes WHERE owner_type='game' AND owner_id=? AND node_type!='memory_atom'",
                (self._game_id,),
            )).fetchall()
        return [str(row[0]) for row in rows]

    async def _get_node_id(self, name: str) -> int | None:
        async with self._connect() as db:
            row = await (await db.execute(
                "SELECT id FROM knowledge_nodes WHERE owner_type='game' AND owner_id=? AND canonical_key=? ORDER BY id LIMIT 1",
                (self._game_id, self._canonicalize(name)),
            )).fetchone()
        return int(row[0]) if row else None

    async def _related(self, node_id: int, relation: str, reverse: bool) -> list[dict]:
        source_col, target_col = ("target_node_id", "source_node_id") if reverse else ("source_node_id", "target_node_id")
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(
                f"""
                SELECT n.*, e.confidence, e.effective_strength
                FROM knowledge_edges e JOIN knowledge_nodes n ON n.id=e.{target_col}
                WHERE e.{source_col}=? AND e.relation=? AND e.status='active'
                ORDER BY e.effective_strength DESC
                """,
                (node_id, relation),
            )).fetchall()
        return [self._node_dict(row) for row in rows]

    @staticmethod
    def _canonicalize(name: str) -> str:
        return name.strip().lower().replace(" ", "")

    @staticmethod
    def _node_dict(row: aiosqlite.Row) -> dict:
        return {
            "id": int(row["id"]),
            "node_type": str(row["node_type"]),
            "name": str(row["label"]),
            "properties": json.loads(row["properties"] or "{}"),
            **({"confidence": float(row["confidence"])} if "confidence" in row.keys() else {}),
        }


async def recompute_edge_strengths(db: aiosqlite.Connection) -> int:
    """Aggregate decayed supporting/contradicting atoms into edge strength."""

    db.row_factory = aiosqlite.Row
    edges = await (await db.execute("SELECT id FROM knowledge_edges")).fetchall()
    now = time.time()
    updated = 0
    for edge in edges:
        evidence = await (await db.execute(
            """
            SELECT ev.stance,ev.evidence_weight,a.importance,a.confidence,a.created_at,
                   a.last_reinforced_at,a.ttl_days,a.decay_type,a.reinforcement_count,a.status
            FROM knowledge_edge_evidence ev JOIN memory_atoms a ON a.id=ev.atom_id
            WHERE ev.edge_id=? AND a.status NOT IN ('forgotten','archived')
            """,
            (int(edge["id"]),),
        )).fetchall()
        supports: list[float] = []
        contradicts: list[float] = []
        for item in evidence:
            anchor = float(item["last_reinforced_at"] or item["created_at"])
            days = max(0.0, (now - anchor) / 86400.0)
            temporal = compute_decay_score(item["decay_type"], float(item["ttl_days"]), days)
            strength = min(1.0, float(item["importance"]) * float(item["confidence"]) * temporal * (1.0 + min(0.5, int(item["reinforcement_count"]) * 0.1)) * float(item["evidence_weight"]))
            (contradicts if item["stance"] == "contradicts" else supports).append(strength)
        support_score = 1.0 - math.prod(1.0 - value for value in supports) if supports else 0.0
        contradict_score = 1.0 - math.prod(1.0 - value for value in contradicts) if contradicts else 0.0
        effective = max(0.0, min(1.0, support_score - contradict_score))
        status = "active" if effective >= 0.25 else "dormant" if effective >= 0.05 else "archived"
        await db.execute("UPDATE knowledge_edges SET effective_strength=?,status=? WHERE id=?", (effective, status, int(edge["id"])))
        updated += 1
    await db.commit()
    return updated


__all__ = [
    "GameKnowledgeGraph",
    "attach_atom_to_graph",
    "expand_graph_from_atoms",
    "expand_user_graph_from_atoms",
    "initialize_knowledge_schema",
    "recompute_edge_strengths",
]
