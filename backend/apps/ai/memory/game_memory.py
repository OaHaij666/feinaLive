"""异步记忆总结服务 - 定期总结共享存储中的历史数据

触发条件: 记录数量达到阈值
处理内容:
1. 收集所有历史数据
2. 调用专用总结 LLM
3. 通过 ToolCall 更新三层记忆（核心/重要/近期）
"""

import asyncio
import json
import logging
import time

from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
from apps.ai.shared_context import SharedContext, get_shared_context
from apps.config import config

logger = logging.getLogger(__name__)

MEMORY_SUMMARY_PROMPT = """你需要帮AI游戏主播总结记忆上下文。请分析以下直播内容，更新三层记忆。

【核心记忆】
{current_core}

【重要记忆】
{current_important}

【近期记忆】
{current_recent}

【主播历史】
{host_history}

【游戏历史】
{game_history}

## 可用工具

### 1. search_replace_memory - 搜索替换记忆
参数:
- memory_type: "core" | "important" | "recent"
- mode: "exact" | "fuzzy" | "range"
- search: 搜索内容
- replace: 替换内容
- end: 结束内容（仅range模式）

模式说明:
- exact: 精确匹配，search必须与原文完全一致
- fuzzy: 模糊匹配，忽略大小写和空白差异
- range: 范围替换，替换包括首尾的，从search到end之间的所有内容

示例:
- 精确替换: {"memory_type":"core", "mode":"exact", "search":"防御牌", "replace":"防御牌+5格挡"}
- 模糊替换: {"memory_type":"core", "mode":"fuzzy", "search":"防御牌", "replace":"防御牌加格挡"}
- 范围替换: {"memory_type":"important", "mode":"range", "search":"【牌组】", "end":"【遗物】", "replace":"【牌组】新内容【遗物】"}

### 2. rewrite_memory - 完全重写记忆
参数:
- memory_type: "core" | "important" | "recent"
- content: 新的完整内容


注意:
1. 核心记忆要保留所有已确认的游戏规则
2. 重要记忆要提炼要点，删除冗余
3. 近期记忆保留关键操作即可"""

MEMORY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_replace_memory",
            "description": "搜索并替换记忆内容，支持三种模式",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_type": {
                        "type": "string",
                        "enum": ["core", "important", "recent"],
                        "description": "目标记忆层级",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["exact", "fuzzy", "range"],
                        "description": "匹配模式: exact=精确匹配, fuzzy=模糊匹配(忽略大小写/空白), range=范围替换(需提供end)",
                    },
                    "search": {
                        "type": "string",
                        "description": "搜索内容（range模式时为起始内容）",
                    },
                    "replace": {
                        "type": "string",
                        "description": "替换内容",
                    },
                    "end": {
                        "type": "string",
                        "description": "结束内容（仅range模式需要，替换从search到end之间的所有内容）",
                    },
                },
                "required": ["memory_type", "mode", "search", "replace"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rewrite_memory",
            "description": "完全重写某层记忆，适用于总结后重新组织",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_type": {
                        "type": "string",
                        "enum": ["core", "important", "recent"],
                        "description": "目标记忆层级",
                    },
                    "content": {
                        "type": "string",
                        "description": "新的完整内容",
                    },
                },
                "required": ["memory_type", "content"],
            },
        },
    },
]


class MemorySummarizer:
    def __init__(
        self,
        shared_context: SharedContext | None = None,
        trigger_threshold: int = 30,
        check_interval: float = 60.0,
    ):
        self._shared_context = shared_context or get_shared_context()
        self._trigger_threshold = trigger_threshold
        self._check_interval = check_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_summary_time: float = 0

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self):
        if self._running:
            logger.warning("记忆总结服务已在运行")
            return

        self._running = True
        self._task = asyncio.create_task(self._summarizer_loop())
        logger.info("记忆总结服务启动")

    async def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("记忆总结服务停止")

    async def _summarizer_loop(self):
        while self._running:
            try:
                should_run = await self._should_summarize()
                if should_run:
                    await self._run_summary()

                await asyncio.sleep(self._check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"记忆总结异常: {e}", exc_info=True)
                await asyncio.sleep(30)

    async def _should_summarize(self) -> bool:
        host_entries = await self._shared_context.get_host_history(limit=100)
        game_entries = await self._shared_context.get_game_history(limit=100)
        total = len(host_entries) + len(game_entries)

        if total >= self._trigger_threshold:
            return True

        elapsed = time.time() - self._last_summary_time
        if elapsed > 300 and total > 5:
            return True

        return False

    async def _run_summary(self):
        host_entries = await self._shared_context.get_host_history(limit=100)
        game_entries = await self._shared_context.get_game_history(limit=100)
        memory = await self._shared_context.get_memory()

        host_lines = []
        for e in host_entries:
            host_lines.append(f"观众: {e.danmaku} | 主播: {e.reply}")

        game_lines = []
        for e in game_entries:
            game_lines.append(f"{e.action}({e.params}) -> {e.result}")

        prompt = MEMORY_SUMMARY_PROMPT.format(
            current_core=memory.core or "（暂无）",
            current_important=memory.important or "（暂无）",
            current_recent=memory.recent or "（暂无）",
            host_history="\n".join(host_lines[-20:]) or "（暂无）",
            game_history="\n".join(game_lines[-20:]) or "（暂无）",
        )

        ai = get_ai_client()
        if not ai.available:
            logger.warning("AI 不可用，跳过记忆总结")
            return

        messages = [ChatMessage(role="user", content=prompt)]
        request = ChatRequest(
            messages=messages,
            model=config.llm_model,
            temperature=0.3,
            max_tokens=500,
            tools=MEMORY_TOOLS,
        )

        try:
            response = await ai.chat(request)
            if response and response.tool_calls:
                await self._execute_memory_tools(response.tool_calls)
                await self._shared_context.trim_histories(keep_seconds=300)
                self._last_summary_time = time.time()
                logger.info("记忆总结完成")
        except Exception as e:
            logger.error(f"记忆总结失败: {e}")

    async def _execute_memory_tools(self, tool_calls: list):
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            try:
                args = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, KeyError):
                logger.warning(f"Tool 参数解析失败: {tc}")
                continue

            if name == "search_replace_memory":
                await self._shared_context.search_replace_memory(
                    memory_type=args["memory_type"],
                    mode=args["mode"],
                    search=args["search"],
                    replace=args["replace"],
                    end=args.get("end", ""),
                )
            elif name == "rewrite_memory":
                await self._shared_context.rewrite_memory(
                    memory_type=args["memory_type"],
                    content=args["content"],
                )
            else:
                logger.warning(f"未知记忆工具: {name}")


_memory_summarizer: MemorySummarizer | None = None


def get_memory_summarizer() -> MemorySummarizer:
    global _memory_summarizer
    if _memory_summarizer is None:
        _memory_summarizer = MemorySummarizer()
    return _memory_summarizer
