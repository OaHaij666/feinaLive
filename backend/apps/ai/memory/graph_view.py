"""记忆调试台图谱视图构建器。

把本项目已有的长期记忆原子和游戏知识图谱动态合并成前端可视化快照。
"""

from __future__ import annotations

import json
from typing import Any

import aiosqlite

from apps.ai.memory.atom_store import AtomStore


class MemoryGraphViewBuilder:
    def __init__(self, db_path: str, store: AtomStore):
        self._db_path = db_path
        self._store = store

    async def graph_counts(self, game_id: str | None = None) -> dict[str, int]:
        filters = []
        params: list[Any] = []
        if game_id:
            filters.append("game_id = ?")
            params.append(game_id)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

        try:
            async with aiosqlite.connect(self._db_path) as db:
                node_row = await (
                    await db.execute(
                        f"SELECT COUNT(*) FROM graph_nodes {where_clause}",
                        params,
                    )
                ).fetchone()
                edge_row = await (
                    await db.execute(
                        f"SELECT COUNT(*) FROM graph_edges {where_clause}",
                        params,
                    )
                ).fetchone()
        except Exception:
            return {"graph_nodes": 0, "graph_edges": 0}

        return {
            "graph_nodes": int(node_row[0]) if node_row else 0,
            "graph_edges": int(edge_row[0]) if edge_row else 0,
        }

    async def overview(
        self,
        *,
        game_id: str | None = None,
        user_id: str | None = None,
        atom_type: str | None = None,
        status: str = "active",
        limit_atoms: int = 40,
        limit_game_nodes: int = 80,
        limit_edges: int = 140,
    ) -> dict[str, Any]:
        atoms_page = await self._store.list_atoms(
            page=1,
            page_size=limit_atoms,
            status=status or "active",
            atom_type=atom_type,
            game_id=game_id,
            user_id=user_id,
            sort="importance_desc",
        )
        game = await self._load_game_graph(
            game_id=game_id,
            query="",
            limit_nodes=limit_game_nodes,
            limit_edges=limit_edges,
        )
        return self._build_payload(
            atoms=atoms_page["items"],
            game_nodes=game["nodes"],
            game_edges=game["edges"],
            mode="overview",
            query=None,
            filters={
                "game_id": game_id,
                "user_id": user_id,
                "atom_type": atom_type,
                "status": status,
            },
        )

    async def query(
        self,
        *,
        query: str = "",
        memory_id: int | None = None,
        game_id: str | None = None,
        user_id: str | None = None,
        atom_type: str | None = None,
        status: str = "active",
        limit_atoms: int = 40,
        limit_game_nodes: int = 80,
        limit_edges: int = 140,
    ) -> dict[str, Any]:
        if memory_id is not None:
            atom = await self._store.get(memory_id)
            atoms = [AtomStore._atom_to_dict(atom)] if atom else []
        else:
            atoms_page = await self._store.list_atoms(
                page=1,
                page_size=limit_atoms,
                keyword=query,
                status=status or "active",
                atom_type=atom_type,
                game_id=game_id,
                user_id=user_id,
                sort="importance_desc",
            )
            atoms = atoms_page["items"]

        game = await self._load_game_graph(
            game_id=game_id,
            query=query,
            limit_nodes=limit_game_nodes,
            limit_edges=limit_edges,
        )
        return self._build_payload(
            atoms=atoms,
            game_nodes=game["nodes"],
            game_edges=game["edges"],
            mode="memory_focus" if memory_id is not None else "query",
            query=query or None,
            memory_id=memory_id,
            filters={
                "game_id": game_id,
                "user_id": user_id,
                "atom_type": atom_type,
                "status": status,
            },
        )

    async def _load_game_graph(
        self,
        *,
        game_id: str | None,
        query: str,
        limit_nodes: int,
        limit_edges: int,
    ) -> dict[str, list[dict[str, Any]]]:
        filters = []
        params: list[Any] = []
        if game_id:
            filters.append("game_id = ?")
            params.append(game_id)
        if query:
            filters.append("(name LIKE ? OR properties LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like])
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

        try:
            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row
                node_rows = await (
                    await db.execute(
                        f"""
                        SELECT *
                        FROM graph_nodes
                        {where_clause}
                        ORDER BY updated_at DESC, id DESC
                        LIMIT ?
                        """,
                        (*params, max(1, min(limit_nodes, 500))),
                    )
                ).fetchall()
                node_ids = [int(row["id"]) for row in node_rows]
                if not node_ids:
                    return {"nodes": [], "edges": []}

                node_placeholders = ",".join("?" * len(node_ids))
                edge_filters = [
                    f"source_id IN ({node_placeholders})",
                    f"target_id IN ({node_placeholders})",
                ]
                edge_params: list[Any] = [*node_ids, *node_ids]
                if game_id:
                    edge_filters.append("game_id = ?")
                    edge_params.append(game_id)
                edge_rows = await (
                    await db.execute(
                        f"""
                        SELECT *
                        FROM graph_edges
                        WHERE {' AND '.join(edge_filters)}
                        ORDER BY confidence DESC, id DESC
                        LIMIT ?
                        """,
                        (*edge_params, max(1, min(limit_edges, 500))),
                    )
                ).fetchall()
        except Exception:
            return {"nodes": [], "edges": []}

        return {
            "nodes": [self._game_node_to_dict(row) for row in node_rows],
            "edges": [self._game_edge_to_dict(row) for row in edge_rows],
        }

    def _build_payload(
        self,
        *,
        atoms: list[dict[str, Any]],
        game_nodes: list[dict[str, Any]],
        game_edges: list[dict[str, Any]],
        mode: str,
        query: str | None,
        memory_id: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[str, dict[str, Any]] = {}
        memories: list[dict[str, Any]] = []
        entity_to_node_id: dict[str, str] = {}
        game_canonical_to_id: dict[str, str] = {}

        for node in game_nodes:
            node_id = f"game:{node['id']}"
            canonical = self._canonicalize(node["name"])
            game_canonical_to_id[canonical] = node_id
            nodes[node_id] = {
                "id": node_id,
                "type": f"game_{node['node_type']}",
                "label": node["name"],
                "weight": 2.0,
                "degree": 0,
                "metadata": node,
            }

        for edge in game_edges:
            edge_id = f"gameedge:{edge['id']}"
            source = f"game:{edge['source_id']}"
            target = f"game:{edge['target_id']}"
            if source not in nodes or target not in nodes:
                continue
            edges[edge_id] = {
                "id": edge_id,
                "source": source,
                "target": target,
                "relation_type": edge["relation"],
                "weight": max(0.3, float(edge.get("confidence") or 0.7) * 2),
                "confidence": float(edge.get("confidence") or 0.7),
                "metadata": edge,
            }

        for atom in atoms:
            atom_id = int(atom["id"])
            node_id = f"atom:{atom_id}"
            nodes[node_id] = {
                "id": node_id,
                "type": "atom",
                "label": f"#{atom_id} {atom['atom_type']}",
                "weight": 1.0 + float(atom.get("importance") or 0.5) * 2,
                "degree": 0,
                "metadata": atom,
            }
            memories.append(
                {
                    "memory_id": atom_id,
                    "summary": atom.get("content", ""),
                    "atom_type": atom.get("atom_type"),
                    "importance": atom.get("importance"),
                    "status": atom.get("status"),
                    "game_id": atom.get("game_id"),
                    "user_id": atom.get("user_id"),
                    "created_at": atom.get("created_at"),
                }
            )

            for entity in atom.get("entities") or []:
                entity_text = str(entity).strip()
                if not entity_text:
                    continue
                canonical = self._canonicalize(entity_text)
                entity_id = entity_to_node_id.setdefault(canonical, f"entity:{canonical}")
                nodes.setdefault(
                    entity_id,
                    {
                        "id": entity_id,
                        "type": "entity",
                        "label": entity_text,
                        "weight": 1.2,
                        "degree": 0,
                        "metadata": {"canonical": canonical},
                    },
                )
                edges[f"mentions:{atom_id}:{canonical}"] = {
                    "id": f"mentions:{atom_id}:{canonical}",
                    "source": node_id,
                    "target": entity_id,
                    "relation_type": "mentions",
                    "weight": 1.0,
                    "confidence": atom.get("confidence", 0.7),
                    "memory_id": atom_id,
                    "metadata": {"entity": entity_text},
                }
                game_node_id = game_canonical_to_id.get(canonical)
                if game_node_id:
                    edges[f"matches:{canonical}:{game_node_id}"] = {
                        "id": f"matches:{canonical}:{game_node_id}",
                        "source": entity_id,
                        "target": game_node_id,
                        "relation_type": "matches",
                        "weight": 0.8,
                        "confidence": 1.0,
                        "metadata": {"canonical": canonical},
                    }

        for edge in edges.values():
            if edge["source"] in nodes:
                nodes[edge["source"]]["degree"] += 1
            if edge["target"] in nodes:
                nodes[edge["target"]]["degree"] += 1

        node_list = sorted(
            nodes.values(),
            key=lambda item: (
                -float(item.get("weight") or 0),
                -int(item.get("degree") or 0),
                str(item.get("label") or ""),
            ),
        )
        edge_list = list(edges.values())
        node_type_breakdown: dict[str, int] = {}
        relation_breakdown: dict[str, int] = {}
        for node in node_list:
            node_type = str(node["type"])
            node_type_breakdown[node_type] = node_type_breakdown.get(node_type, 0) + 1
        for edge in edge_list:
            relation = str(edge["relation_type"])
            relation_breakdown[relation] = relation_breakdown.get(relation, 0) + 1

        return {
            "enabled": True,
            "mode": mode,
            "query": query,
            "memory_id": memory_id,
            "filters": filters or {},
            "summary": {
                "visible_node_count": len(node_list),
                "visible_edge_count": len(edge_list),
                "visible_memory_count": len(memories),
                "node_type_breakdown": node_type_breakdown,
                "relation_breakdown": relation_breakdown,
            },
            "top_nodes": node_list[:8],
            "top_memories": memories[:8],
            "snapshot": {
                "nodes": node_list,
                "edges": edge_list,
                "memories": memories,
            },
        }

    @staticmethod
    def _game_node_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "game_id": row["game_id"],
            "node_type": row["node_type"],
            "name": row["name"],
            "canonical_name": row["canonical_name"],
            "properties": _from_json(row["properties"]),
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
        }

    @staticmethod
    def _game_edge_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "game_id": row["game_id"],
            "source_id": int(row["source_id"]),
            "target_id": int(row["target_id"]),
            "relation": row["relation"],
            "confidence": float(row["confidence"]),
            "evidence": row["evidence"],
            "created_at": float(row["created_at"]),
        }

    @staticmethod
    def _canonicalize(value: str) -> str:
        return "".join(str(value).strip().lower().split())


def _from_json(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        data = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


__all__ = ["MemoryGraphViewBuilder"]
