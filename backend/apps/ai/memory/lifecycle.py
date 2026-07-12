"""记忆原子生命周期管理 — 过期/遗忘/清理 + 强化匹配"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from apps.ai.memory.atom_store import AtomStore

logger = logging.getLogger(__name__)


class AtomLifecycleManager:
    """定期执行记忆原子的生命周期维护"""

    def __init__(
        self,
        atom_store: AtomStore,
        config: dict[str, Any] | None = None,
    ):
        self.atom_store = atom_store
        self.config = config or {}
        self._maintenance_interval_hours = float(
            self.config.get("atom_maintenance_interval_hours", 24.0)
        )
        self._forget_delay_days = float(self.config.get("atom_forget_delay_days", 7.0))
        self._purge_delay_days = float(
            self.config.get(
                "atom_purge_delay_days",
                max(self._forget_delay_days * 4.0, 30.0),
            )
        )
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._maintenance_loop())
        logger.info("AtomLifecycleManager 启动")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("AtomLifecycleManager 停止")

    async def _maintenance_loop(self) -> None:
        while self._running:
            try:
                await self.run_maintenance()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("生命周期维护异常", exc_info=True)
                await asyncio.sleep(60.0)
                continue
            await asyncio.sleep(self._maintenance_interval_hours * 3600.0)

    async def run_maintenance(self) -> dict[str, int]:
        """执行一次完整维护，返回各操作计数"""
        result: dict[str, int] = {}

        expired = await self.atom_store.expire_stale_atoms()
        result["expired"] = expired

        forgotten = await self.atom_store.forget_expired_atoms(self._forget_delay_days)
        result["forgotten"] = forgotten

        purged = await self.atom_store.cleanup_forgotten(self._purge_delay_days)
        result["purged"] = purged

        result["graph_edges_recomputed"] = await self.atom_store.recompute_graph_strengths()
        result["vector_metadata_synced"] = await self.atom_store.reconcile_vector_metadata()

        if any(v > 0 for v in result.values()):
            logger.info(f"生命周期维护完成: {result}")

        return result

    async def run_manual_reinforcement(
        self,
        new_atoms: list,
        similarity_threshold: float = 0.6,
    ) -> int:
        """查找与新原子相似的已有原子并强化

        使用 Jaccard 相似度匹配，CJK 文本使用字符 bigram 回退
        """
        if not new_atoms:
            return 0

        reinforced = 0
        for new_atom in new_atoms:
            content = str(new_atom.content)
            new_tokens = set(content.lower().split())
            # CJK 或短文本使用字符 bigram
            if len(new_tokens) < 3:
                chars = content.replace(" ", "")
                if len(chars) >= 4:
                    new_tokens = {chars[i : i + 2] for i in range(len(chars) - 1)}

            if len(new_tokens) < 2:
                continue

            search_query = " ".join(list(new_tokens)[:8])
            existing = await self.atom_store.search_fts(
                search_query,
                limit=5,
                game_id=getattr(new_atom, "game_id", None),
                user_id=getattr(new_atom, "user_id", None),
                include_expired=False,
            )
            for ex in existing:
                ex_content = ex.content.lower()
                ex_tokens = set(ex_content.split())
                if len(ex_tokens) < 2:
                    ex_tokens = (
                        {ex_content[i : i + 2] for i in range(len(ex_content) - 1)}
                        if len(ex_content) >= 4
                        else set()
                    )
                if not ex_tokens or not new_tokens:
                    continue
                jaccard = len(new_tokens & ex_tokens) / max(
                    1, len(new_tokens | ex_tokens)
                )
                if jaccard >= similarity_threshold:
                    await self.atom_store.reinforce(
                        ex.atom_id,
                        new_confidence=float(getattr(new_atom, "confidence", 0.7)),
                    )
                    reinforced += 1
                    break

        return reinforced


__all__ = ["AtomLifecycleManager"]
