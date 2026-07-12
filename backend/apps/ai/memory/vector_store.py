"""ChromaDB adapter. SQLite remains the source of truth."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


class ChromaVectorStore:
    def __init__(self, path: str, collection_name: str = "memory_atoms"):
        self.path = str(Path(path).resolve())
        self.collection_name = collection_name
        self._client: Any = None
        self._collection: Any = None

    @property
    def available(self) -> bool:
        return self._collection is not None

    async def initialize(self) -> None:
        def _open() -> tuple[Any, Any]:
            import chromadb

            Path(self.path).mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=self.path)
            collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine", "source_of_truth": "sqlite"},
            )
            return client, collection

        self._client, self._collection = await asyncio.to_thread(_open)

    async def close(self) -> None:
        self._collection = None
        self._client = None

    async def upsert(
        self,
        atom_id: int,
        embedding: list[float],
        document: str,
        metadata: dict[str, Any],
    ) -> None:
        if not self._collection:
            return
        current_dimension = self._collection.metadata.get("embedding_dimension")
        if current_dimension and int(current_dimension) != len(embedding):
            raise ValueError(
                f"Embedding 维度从 {current_dimension} 变为 {len(embedding)}，请重建 ChromaDB 索引"
            )
        if not current_dimension:
            collection_metadata = dict(self._collection.metadata)
            collection_metadata.pop("hnsw:space", None)
            collection_metadata["embedding_dimension"] = len(embedding)
            await asyncio.to_thread(
                self._collection.modify, metadata=collection_metadata
            )
        clean = {key: value for key, value in metadata.items() if value is not None}
        await asyncio.to_thread(
            self._collection.upsert,
            ids=[str(atom_id)],
            embeddings=[embedding],
            documents=[document],
            metadatas=[clean],
        )

    async def update_metadata(self, atom_id: int, metadata: dict[str, Any]) -> None:
        if not self._collection:
            return
        clean = {key: value for key, value in metadata.items() if value is not None}
        await asyncio.to_thread(
            self._collection.update, ids=[str(atom_id)], metadatas=[clean]
        )

    async def delete(self, atom_ids: list[int]) -> None:
        if self._collection and atom_ids:
            await asyncio.to_thread(
                self._collection.delete, ids=[str(atom_id) for atom_id in atom_ids]
            )

    async def existing_ids(self) -> set[int]:
        if not self._collection:
            return set()
        result = await asyncio.to_thread(self._collection.get, include=[])
        return {int(value) for value in result.get("ids", [])}

    async def query(
        self,
        embedding: list[float],
        limit: int,
        *,
        game_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        atom_types: list[str] | None = None,
        include_inactive: bool = False,
    ) -> dict[int, float]:
        if not self._collection or not embedding:
            return {}
        count = await asyncio.to_thread(self._collection.count)
        if count <= 0:
            return {}
        clauses: list[dict[str, Any]] = []
        if not include_inactive:
            clauses.append({"status": "active"})
        if game_id is not None:
            clauses.append({"game_id": game_id})
        if user_id is not None:
            clauses.append({"user_id": user_id})
        if session_id is not None:
            clauses.append({"session_id": session_id})
        if atom_types:
            clauses.append({"atom_type": {"$in": atom_types}})
        where = clauses[0] if len(clauses) == 1 else {"$and": clauses} if clauses else None
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": min(max(1, limit), count),
            "include": ["distances"],
        }
        if where:
            kwargs["where"] = where
        result = await asyncio.to_thread(self._collection.query, **kwargs)
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        scores = {
            int(atom_id): max(0.0, 1.0 - float(distance))
            for atom_id, distance in zip(ids, distances)
        }
        return {atom_id: score for atom_id, score in scores.items() if score >= 0.2}

    async def status(self) -> dict[str, Any]:
        count = await asyncio.to_thread(self._collection.count) if self._collection else 0
        return {
            "engine": "chromadb",
            "available": self.available,
            "path": self.path,
            "collection": self.collection_name,
            "vector_count": count,
            "embedding_dimension": (
                self._collection.metadata.get("embedding_dimension")
                if self._collection
                else None
            ),
        }

    async def reset(self) -> None:
        if not self._client:
            return

        def _reset() -> Any:
            self._client.delete_collection(self.collection_name)
            return self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine", "source_of_truth": "sqlite"},
            )

        self._collection = await asyncio.to_thread(_reset)


__all__ = ["ChromaVectorStore"]
