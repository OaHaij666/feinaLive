"""记忆调试台 API。"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.ai.memory.atom import AtomStatus, AtomType
from apps.ai.memory.engine import get_memory_engine
from apps.ai.memory.graph_view import MemoryGraphViewBuilder

router = APIRouter(prefix="/ai/memory", tags=["ai-memory"])


class AtomUpdateRequest(BaseModel):
    content: str | None = None
    atom_type: str | None = None
    entities: list[str] | None = None
    importance: float | None = None
    confidence: float | None = None
    status: str | None = None
    game_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] | None = None


class BatchUpdateRequest(BaseModel):
    atom_ids: list[int] = Field(default_factory=list)
    fields: dict[str, Any] = Field(default_factory=dict)


class BatchDeleteRequest(BaseModel):
    atom_ids: list[int] = Field(default_factory=list)


class RecallTestRequest(BaseModel):
    query: str = ""
    k: int = 5
    game_id: str | None = None
    user_id: str | None = None
    atom_type: str | None = None


class GraphQueryRequest(BaseModel):
    query: str = ""
    memory_id: int | None = None
    game_id: str | None = None
    user_id: str | None = None
    atom_type: str | None = None
    status: str = "active"
    limit_atoms: int = 40
    limit_game_nodes: int = 80
    limit_edges: int = 140


class InjectPreviewRequest(BaseModel):
    target: str = "game"
    game_id: str = "slay_the_spire"
    user_id: str | None = None
    query: str = ""


@router.get("/stats")
async def get_memory_stats():
    engine = get_memory_engine()
    atom_stats = await engine.store.get_statistics()
    graph_counts = await _graph_builder().graph_counts()
    session = engine.session
    return {
        **atom_stats,
        **graph_counts,
        "session": {
            "active": session.active,
            "core_length": len(session.core),
            "important_length": len(session.important),
            "recent_length": len(session.recent),
            "pending_count": len(session.pending_events),
            "summarized_until_id": session.summarized_until_id,
        },
    }


@router.get("/atoms")
async def list_atoms(
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    status: str = "all",
    atom_type: str | None = None,
    game_id: str | None = None,
    user_id: str | None = None,
    sort: str = "created_desc",
):
    engine = get_memory_engine()
    return await engine.store.list_atoms(
        page=page,
        page_size=page_size,
        keyword=keyword.strip(),
        status=status,
        atom_type=atom_type,
        game_id=game_id,
        user_id=user_id,
        sort=sort,
    )


@router.get("/atoms/{atom_id}")
async def get_atom_detail(atom_id: int):
    atom = await get_memory_engine().store.get(atom_id)
    if atom is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return get_memory_engine().store._atom_to_dict(atom)


@router.patch("/atoms/{atom_id}")
async def update_atom(atom_id: int, request: AtomUpdateRequest):
    fields = request.model_dump(exclude_unset=True)
    try:
        atom = await get_memory_engine().store.update_atom_fields(atom_id, fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if atom is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"success": True, "atom": get_memory_engine().store._atom_to_dict(atom)}


@router.post("/atoms/batch-update")
async def batch_update_atoms(request: BatchUpdateRequest):
    atom_ids = _valid_atom_ids(request.atom_ids)
    if not atom_ids:
        raise HTTPException(status_code=400, detail="需要提供记忆 ID")
    try:
        updated = await get_memory_engine().store.batch_update_fields(
            atom_ids,
            request.fields,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "updated_count": updated, "total": len(atom_ids)}


@router.post("/atoms/batch-delete")
async def batch_delete_atoms(request: BatchDeleteRequest):
    atom_ids = _valid_atom_ids(request.atom_ids)
    if not atom_ids:
        raise HTTPException(status_code=400, detail="需要提供记忆 ID")
    deleted = await get_memory_engine().store.batch_update_status(
        atom_ids,
        AtomStatus.FORGOTTEN,
    )
    return {"success": True, "deleted_count": deleted, "total": len(atom_ids)}


@router.post("/recall/test")
async def test_recall(request: RecallTestRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="查询内容不能为空")
    atom_types = None
    if request.atom_type:
        try:
            atom_types = [AtomType(request.atom_type)]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="记忆类型无效") from exc

    start = time.perf_counter()
    results = await get_memory_engine().recall(
        query=query,
        k=max(1, min(request.k, 50)),
        game_id=request.game_id,
        user_id=request.user_id,
        atom_types=atom_types,
    )
    elapsed = (time.perf_counter() - start) * 1000
    return {
        "query": query,
        "k": max(1, min(request.k, 50)),
        "elapsed_time_ms": round(elapsed, 2),
        "total": len(results),
        "results": [
            {
                **get_memory_engine().store._atom_to_dict(atom),
                "final_score": round(float(atom.metadata.get("final_score", 0)), 6),
                "bm25_score": round(float(atom.metadata.get("bm25_score", 0)), 6),
                "temporal_score": round(float(atom.metadata.get("temporal_score", 0)), 6),
            }
            for atom in results
        ],
    }


@router.get("/graph/overview")
async def graph_overview(
    game_id: str | None = None,
    user_id: str | None = None,
    atom_type: str | None = None,
    status: str = "active",
    limit_atoms: int = 40,
    limit_game_nodes: int = 80,
    limit_edges: int = 140,
):
    return await _graph_builder().overview(
        game_id=game_id,
        user_id=user_id,
        atom_type=atom_type,
        status=status,
        limit_atoms=limit_atoms,
        limit_game_nodes=limit_game_nodes,
        limit_edges=limit_edges,
    )


@router.post("/graph/query")
async def graph_query(request: GraphQueryRequest):
    return await _graph_builder().query(**request.model_dump())


@router.get("/session")
async def get_session_memory():
    session = get_memory_engine().session
    return {
        "active": session.active,
        "core": session.core,
        "important": session.important,
        "recent": session.recent,
        "pending_events": [
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "content": event.content,
                "metadata": event.metadata,
                "created_at": event.created_at,
            }
            for event in session.pending_events
        ],
        "summarized_until_id": session.summarized_until_id,
    }


@router.post("/inject/preview")
async def inject_preview(request: InjectPreviewRequest):
    engine = get_memory_engine()
    if request.target == "host":
        text = await engine.inject_for_host(
            user_id=request.user_id, query=request.query
        )
    elif request.target == "game":
        await engine.ensure_graph(request.game_id)
        text = await engine.inject_for_game(game_id=request.game_id)
    else:
        raise HTTPException(status_code=400, detail="target 必须是 game 或 host")
    return {
        "target": request.target,
        "game_id": request.game_id,
        "user_id": request.user_id,
        "content": text,
    }


@router.get("/backups")
async def list_backups():
    backup_dir = _backup_dir()
    items = []
    if backup_dir.exists():
        for item in sorted(backup_dir.iterdir(), reverse=True):
            if item.is_dir():
                files = [f for f in item.iterdir() if f.is_file()]
                items.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "file_count": len(files),
                        "size_bytes": sum(f.stat().st_size for f in files),
                        "created_at": item.stat().st_ctime,
                    }
                )
    return {"backups": items}


@router.get("/vector/status")
async def vector_status():
    return await get_memory_engine().store.vector_status()


@router.post("/vector/backfill")
async def vector_backfill(batch_size: int = 50):
    return await get_memory_engine().store.backfill_embeddings(
        max(1, min(batch_size, 500))
    )


@router.post("/vector/rebuild")
async def vector_rebuild(batch_size: int = 100):
    store = get_memory_engine().store
    await store.reset_vector_index()
    return await store.backfill_embeddings(max(1, min(batch_size, 500)))


@router.post("/backups")
async def create_backup():
    db_path = _db_path()
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="SQLite 数据库不存在")
    target_dir = _backup_dir() / time.strftime("%Y%m%d-%H%M%S")
    target_dir.mkdir(parents=True, exist_ok=False)
    target = target_dir / db_path.name

    def _online_backup() -> None:
        source_db = sqlite3.connect(str(db_path))
        target_db = sqlite3.connect(str(target))
        try:
            source_db.backup(target_db)
        finally:
            target_db.close()
            source_db.close()

    await asyncio.to_thread(_online_backup)
    vector = await get_memory_engine().store.vector_status()
    manifest = {
        "created_at": time.time(),
        "database": db_path.name,
        "vector_index": vector,
        "vector_index_is_rebuildable": True,
    }
    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    copied = [
        {"name": target.name, "size_bytes": target.stat().st_size},
        {"name": manifest_path.name, "size_bytes": manifest_path.stat().st_size},
    ]
    return {"success": True, "backup": {"name": target_dir.name, "path": str(target_dir), "files": copied}}


def _graph_builder() -> MemoryGraphViewBuilder:
    engine = get_memory_engine()
    return MemoryGraphViewBuilder(engine.db_path, engine.store)


def _db_path() -> Path:
    return Path(get_memory_engine().db_path).resolve()


def _backup_dir() -> Path:
    return _db_path().parent / "memory_backups"


def _valid_atom_ids(atom_ids: list[int]) -> list[int]:
    return [int(atom_id) for atom_id in atom_ids if int(atom_id) > 0]


__all__ = ["router"]
