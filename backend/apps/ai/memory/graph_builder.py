"""知识图谱构建器 — 独立进程，周期性用 LLM 分析已积累的节点，批量推断关系边

与 memorize 工具解耦：不依赖游戏 AI 是否调用 memorized，而是以自己的节奏扫描
图谱中已经积累的节点，使用专用 LLM 调用批量推断 synergizes_with / countered_by 等关系。

边写入后，下一次 MemoryInjector._build_graph_context 循环就能把协同/克制关系注入 Prompt。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
from apps.ai.memory.atom import AtomType
from apps.ai.memory.atom_store import AtomStore
from apps.ai.memory.graph_store import GameKnowledgeGraph

logger = logging.getLogger(__name__)

# 每次构建最多发给 LLM 的节点数（避免 prompt 过长）
_MAX_NODES_PER_BATCH = 40

_TUNNED_PROMPT = (
    "你是《杀戮尖塔》知识图谱构建器。分析以下游戏实体列表，推断它们之间的结构化关系。\n"
    "\n"
    "可选关系:\n"
    "  synergizes_with — 两个实体存在配合/协同效果\n"
    "  countered_by    — 某个实体可以被另一个克制\n"
    "  belongs_to      — 实体属于某个类别/体系\n"
    "  found_in        — 实体在特定情境下出现\n"
    "\n"
    "已知实体 (格式: 序号. [类型] 名称 | 属性):\n"
    "{nodes}\n"
    "\n"
    "已有边 (不要重复):\n"
    "{edges}\n"
    "\n"
    "返回 JSON: {{"
    '"edges": [{{"source":"实体A","target":"实体B","relation":"关系","evidence":"简短证据"}}]'
    "}}\n"
    "\n"
    "注意:\n"
    "- 只返回有明确逻辑依据的关系，不要猜测\n"
    "- source 和 target 必须与上方实体名称完全一致\n"
    "- 已在「已有边」中列出的不要重复\n"
    "- 如果没有新的关系可推断，返回 {{\"edges\": []}}\n"
)


def _to_node_text(nodes: list[dict]) -> str:
    """把节点列表格式化为 prompt 用的文本"""
    lines: list[str] = []
    for i, n in enumerate(nodes, 1):
        props = n.get("properties", {}) or {}
        parts: list[str] = []
        if "cost" in props:
            parts.append(f"cost={props['cost']}")
        if "type" in props:
            parts.append(f"type={props['type']}")
        if "rarity" in props:
            parts.append(f"rarity={props['rarity']}")
        if "hp" in props or "max_hp" in props:
            parts.append(f"hp={props.get('hp','?')}/{props.get('max_hp','?')}")
        if "intent" in props and props["intent"]:
            parts.append(f"intent={props['intent']}")
        prop_str = ", ".join(parts) if parts else ""
        entry = f"  {i}. [{n.get('node_type', '?')}] {n['name']}"
        if prop_str:
            entry += f" | {prop_str}"
        lines.append(entry)
    return "\n".join(lines)


def _to_edge_text(edges: list[dict]) -> str:
    """把已有边列表格式化为 prompt 用的文本"""
    if not edges:
        return "  (暂无)"
    lines: list[str] = []
    for e in edges:
        lines.append(f"  {e['source']} --[{e.get('relation', '?')}]--> {e['target']}")
    return "\n".join(lines)


class KnowledgeGraphBuilder:
    """知识图谱边推断器 — 独立于游戏循环运行"""

    def __init__(
        self,
        graph: GameKnowledgeGraph,
        store: AtomStore,
        config: dict[str, Any] | None = None,
    ):
        self._graph = graph
        self._store = store
        self._config = config or {}
        self._check_interval_seconds = float(
            self._config.get("graph_check_interval_seconds", 60.0)
        )
        self._min_new_nodes = int(
            self._config.get("graph_min_new_nodes", 5)
        )
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_build_node_count: int = 0
        self._last_build_time: float = 0.0

    @property
    def graph(self) -> GameKnowledgeGraph:
        return self._graph

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._build_loop())
        logger.info(
            "KnowledgeGraphBuilder 启动, min_new_nodes=%s, check_interval=%ss",
            self._min_new_nodes,
            self._check_interval_seconds,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("KnowledgeGraphBuilder 停止")

    async def _build_loop(self) -> None:
        """按新增节点量触发构建循环"""
        await asyncio.sleep(30.0)
        while self._running:
            try:
                current_count = len(await self._graph.get_all_node_names())
                new_nodes = current_count - self._last_build_node_count
                idle_time = time.time() - self._last_build_time

                if current_count < 2:
                    await asyncio.sleep(self._check_interval_seconds)
                    continue

                if (self._last_build_node_count == 0
                        or new_nodes >= self._min_new_nodes):
                    ai = get_ai_client()
                    if ai.available:
                        await self.build_edges()
                        self._last_build_node_count = current_count
                        self._last_build_time = time.time()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("知识图谱构建循环异常", exc_info=True)
            await asyncio.sleep(self._check_interval_seconds)

    async def build_edges(self) -> int:
        """执行一次边推断：拉取全部节点 + 已有边，用 LLM 批量分析并写入新边

        每次构建都发送**全部**节点，让 LLM 看到完整图谱。
        已有边会在 prompt 中标记为「不要重复」，避免浪费。

        Returns:
            本次写入的边数量
        """
        ai = get_ai_client()
        if not ai.available:
            logger.debug("LLM 不可用，跳过图谱构建")
            return 0

        all_nodes = await self._get_all_nodes_with_properties()
        if len(all_nodes) < 2:
            return 0

        existing_edges = await self._get_all_edges()
        entity_hints = await self._get_entity_cooccurrences()

        total_written = 0
        for batch_start in range(0, len(all_nodes), _MAX_NODES_PER_BATCH):
            batch = all_nodes[batch_start: batch_start + _MAX_NODES_PER_BATCH]
            edges_from_batch = await self._infer_edges(
                batch_nodes=batch,
                existing_edges=existing_edges,
                entity_hints=entity_hints,
            )
            written = await self._write_edges(edges_from_batch)
            total_written += written

        if total_written > 0:
            logger.info(
                "图谱构建完成: 分析 %s 个节点, 写入 %s 条边",
                len(all_nodes),
                total_written,
            )

        return total_written

    async def _infer_edges(
        self,
        batch_nodes: list[dict],
        existing_edges: list[dict],
        entity_hints: dict[str, list[str]],
    ) -> list[dict]:
        """调用 LLM 分析一批节点，返回推断的边列表"""
        ai = get_ai_client()

        # 构建 node text + 追加共现提示
        node_lines = []
        for n in batch_nodes:
            name = n["name"]
            line = f"  - [{n.get('node_type', '?')}] {name}"
            props = n.get("properties", {}) or {}
            prop_parts = []
            for k, v in props.items():
                if k == "source":
                    # mechanic 类型有完整描述，直接展示
                    prop_parts.append(f"{v}")
                elif v not in (None, "", [], {}):
                    prop_parts.append(f"{k}={v}")
            if prop_parts:
                line += " | " + ", ".join(prop_parts)
            # 追加共现提示
            if name in entity_hints:
                others = [o for o in entity_hints[name] if o != name]
                if others:
                    line += f" (与 {', '.join(others[:3])} 相关)"
            node_lines.append(line)

        prompt = _TUNNED_PROMPT.format(
            nodes="\n".join(node_lines),
            edges=_to_edge_text(existing_edges),
        )

        try:
            request = ChatRequest(
                messages=[ChatMessage(role="user", content=prompt)],
                model="",
                temperature=0.2,
                max_tokens=800,
                json_format=True,
            )
            response = await ai.chat(request)
            if not response or not response.content:
                return []

            data = json.loads(response.content)
            return data.get("edges", [])

        except json.JSONDecodeError:
            logger.debug("图谱边推断 JSON 解析失败")
            return []
        except Exception as e:
            logger.warning(f"图谱边推断失败: {e}")
            return []

    async def _write_edges(self, edges: list[dict]) -> int:
        """将推断的边写入图谱（跳过无效/重复的）"""
        valid_relations = {"synergizes_with", "countered_by", "belongs_to", "found_in"}
        written = 0
        for edge in edges:
            source = str(edge.get("source", "")).strip()
            target = str(edge.get("target", "")).strip()
            relation = str(edge.get("relation", "")).strip()
            evidence = str(edge.get("evidence", "")).strip()
            if not source or not target or not relation:
                continue
            if relation not in valid_relations:
                continue
            ok = await self._graph.add_edge_by_name(
                source_name=source,
                target_name=target,
                relation=relation,
                confidence=0.7,
                evidence=evidence,
            )
            if ok:
                written += 1
        return written

    async def _get_all_nodes_with_properties(self) -> list[dict]:
        """获取当前 game 下所有节点（含属性）"""
        all_names = await self._graph.get_all_node_names()
        if not all_names:
            return []
        nodes = []
        for name in all_names:
            results = await self._graph.search(name, k=1)
            if results:
                nodes.append(results[0])
            else:
                nodes.append({"name": name, "node_type": "?", "properties": {}})
        return nodes

    async def _get_all_edges(self) -> list[dict]:
        """获取当前 game 下所有已有边，尽量轻量"""
        all_names = await self._graph.get_all_node_names()
        if not all_names:
            return []

        # 用 get_related 间接收集边（它会查询每个节点的协同/克制）
        edges: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for name in all_names[:20]:  # 控制查询量
            # 取得协同
            synergies = await self._graph.get_synergies(name)
            for s in synergies:
                key = (name, s["name"], "synergizes_with")
                if key not in seen:
                    edges.append({"source": name, "target": s["name"], "relation": "synergizes_with"})
                    seen.add(key)
            # 取得克制
            counters = await self._graph.get_countered_by(name)
            for c in counters:
                key = (c["name"], name, "countered_by")
                if key not in seen:
                    edges.append({"source": c["name"], "target": name, "relation": "countered_by"})
                    seen.add(key)

        return edges

    async def _get_entity_cooccurrences(self) -> dict[str, list[str]]:
        """从 AtomStore 中提取游戏知识原子的 entity 共现信息

        如果原子 A 的 entities = ["壁垒", "金属化"]，说明这两个实体被同一个记忆关联。
        """
        hints: dict[str, list[str]] = {}
        try:
            atoms = await self._store.search_fts(
                query="",
                limit=50,
                game_id=self._graph.game_id,
                atom_types=[AtomType.GAME_MECHANIC, AtomType.GAME_LORE],
            )
            for atom in atoms:
                for entity in atom.entities:
                    if entity not in hints:
                        hints[entity] = []
                    for other in atom.entities:
                        if other != entity and other not in hints[entity]:
                            hints[entity].append(other)
        except Exception:
            pass
        return hints
