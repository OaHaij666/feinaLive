"""游戏 Graph - MCP 游戏决策主循环

流程:
1. 数据收集 (并行): MCP游戏状态 + 主播历史 + 游戏历史 + 总记忆
2. 检查缓冲动作: 如有则直接执行（跳过 LLM 决策）
3. 构建提示词: 组合所有上下文 + MCP tools + 内置tool
4. LLM 决策: 生成 tool_calls
5. 执行工具: 非游戏工具并行，游戏工具只执行第一个，其余入缓冲
   - 每个游戏动作间隔 min_step_interval，模拟真人操作节奏
6. 更新历史: 记录本次操作
7. 进入下一轮
"""

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from apps.ai.client import ChatMessage, ChatRequest, get_game_ai_client
from apps.ai.commentary import CommentaryCoordinator
from apps.ai.mcp.base_adapter import BaseGameAdapter, UnifiedAction, UnifiedGameState
from apps.ai.memory.engine import get_memory_engine
from apps.ai.memory.tools import get_memory_tools, handle_memory_tool_call
from apps.ai.shared_context import SharedContext, get_shared_context
from apps.config import config

logger = logging.getLogger(__name__)

NON_GAME_TOOLS = {"request_host_commentary", "request_memory_update", "memorize", "recall"}

READONLY_MCP_TOOLS = {
    "get_game_state", "get_screen_state", "get_available_commands",
    "get_card_info", "get_relic_info", "get_potion_info",
}


def _split_memory_text(memory_text: str) -> tuple[str, str, str]:
    """按 inject_for_game 产出的 section 标记拆分文本为三层

    inject_for_game() 返回的文本包含多个 section:
      【核心记忆】\n...
      【重要记忆】\n...
      【最近记忆】\n...
      【待总结近期事件】\n...
      【游戏经验】\n...
      与【x】协同: ...

    前三个分给 core/important/recent，其余（游戏经验、图谱上下文）追加到 core。
    """
    import re

    core = ""
    important = ""
    recent = ""
    extra: list[str] = []

    # 按 section 头分割
    parts = re.split(r"\n(?=【)", memory_text)
    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        if stripped.startswith("【核心记忆】"):
            core = stripped[len("【核心记忆】"):].strip()
        elif stripped.startswith("【重要记忆】"):
            important = stripped[len("【重要记忆】"):].strip()
        elif stripped.startswith("【最近记忆】"):
            recent = stripped[len("【最近记忆】"):].strip()
        elif stripped.startswith("【待总结近期事件】"):
            recent_extra = stripped[len("【待总结近期事件】"):].strip()
            if recent_extra:
                recent = f"{recent}\n\n{recent_extra}" if recent else recent_extra
        else:
            extra.append(stripped)

    # 将额外内容（游戏经验、图谱上下文）追加到 core
    if extra:
        extra_text = "\n\n".join(extra)
        core = f"{core}\n\n{extra_text}" if core else extra_text

    return core, important, recent


# ========== Tool 定义 ==========
def _commentary_guide(
    seconds_since: float,
    steps_since: int,
    commentary_interval: float,
    min_step_interval: float,
) -> str:
    suggested_steps = max(1, int(commentary_interval / min_step_interval))
    if seconds_since >= 86400:
        time_hint = "这是本轮游戏第一次解说"
    else:
        time_hint = f"距上次解说已过 {seconds_since:.0f} 秒（{steps_since} 个游戏动作前）"

    return (
        f"- {time_hint}\n"
        f"- ⚠️ 请求解说间隔必须 ≥ {commentary_interval:.0f} 秒（约 {suggested_steps} 个动作）。"
        f"距上次解说不足 {commentary_interval:.0f} 秒时，禁止调用 request_host_commentary\n"
        "- ★ 里程碑事件一定要解说：拿新卡/遗物时、BOSS战、通关、危急时刻\n"
        "- 战斗中的小操作（出一张牌）不需要解说\n"
        "- 同一画面（如仍在同一奖励页/商店页）不要重复解说\n"
        "- key_points 列出解说要点，主播会用自己的风格表达\n"
        "- mood 可以选 excited/confident/nervous/happy/neutral\n"
    )


def _memory_prompt(eagerness: int) -> str:
    base = "调用 request_memory_update 把重要信息写入记忆，mode=rewrite 完全重写，mode=search_replace 搜索替换。\n"
    base += "三层记忆在下次决策时可见:\n"
    base += "- core=游戏机制规律发现\n"
    base += "- important=当前牌组/遗物评估（最重要，每次牌组变化都要更新）\n"
    base += "- recent=近期战术路线\n"

    if eagerness <= 1:
        base += "\n只在发现重大机制规律时 rewrite core，极少调用。"
    elif eagerness <= 2:
        base += "\n拿到新卡/遗物后 rewrite important，发现机制规律时 rewrite core。"
    elif eagerness <= 3:
        base += "\n【何时必须调用】\n"
        base += "- ★ 选牌/拿新卡后：在同一轮决策中同时调用 request_memory_update rewrite important\n"
        base += "  例: 拿到剑柄打击 → rewrite important => \"牌组:5打击4防御1痛击+剑柄打击\"\n"
        base += "- ★ 拿到新遗物后：rewrite important，追加遗物信息\n"
        base += "- ★ 发现卡牌间联动协同（如\"双发+旋风斩=AOE清场\"）：rewrite recent 记录战术构思\n"
        base += "- 牌组小幅变化：search_replace 修正 important\n"
        base += "  例: search=\"5打击\" replace=\"4打击+1完美打击\"\n"
        base += "- 发现机制规律：rewrite core，但要确实验证过\n"
        base += "- 新游戏开始记忆自动清空，不用手动处理"
    elif eagerness <= 4:
        base += "\n拿到新卡/遗物立即 rewrite important，每层结束更新 recent，有发现就记。"
    else:
        base += "\n积极记录一切新信息！新卡/遗物 → important，每层战术 → recent，发现机制 → core。一有新发现立刻调用。"
    return base


def build_game_system_prompt(
    core_memory: str = "",
    important_memory: str = "",
    recent_memory: str = "",
    game_history: str = "",
    host_history: str = "",
    game_state: str = "",
    seconds_since_commentary: float = 0,
    steps_since_commentary: int = 0,
    commentary_interval: float = 30.0,
    min_step_interval: float = 15.0,
    memory_eagerness: int = 3,
) -> str:
    commentary_guide = _commentary_guide(
        seconds_since=seconds_since_commentary,
        steps_since=steps_since_commentary,
        commentary_interval=commentary_interval,
        min_step_interval=min_step_interval,
    )
    memory_section = _memory_prompt(memory_eagerness)

    return f"""你是杀戮尖塔游戏AI，控制主播玩游戏并与观众互动。

【你的双重角色】
你是"游戏操作者"也是"主播的幕后智囊"。
- 游戏操作：用 MCP 工具推进游戏
- 主播互动：用 request_host_commentary 让主播解说，用 request_memory_update 记录情报

【战斗核心原则】
- ★ 斩杀优先：**如果能用攻击牌在本回合击杀敌人，优先击杀**——杀死敌人等于永久消除其伤害，比叠格挡更有效
- 敌人意图为 ATTACK 时，格挡量 >= 敌人预计伤害才能结束回合；但如果能斩杀所有敌人则无需叠格挡
- 只有在敌人无攻击意图（正在BUFF/DEBUFF/准备技能）时才全力输出
- 3费回合：优先出1-2张防御牌保命，剩余费用打输出，不要把所有费都用来攻击
- ★ 敌人编号从 0 开始：2 个敌人的有效 target_index 是 0 和 1（不是 1 和 2）
- ★ 斩杀多个敌人时注意 index 漂移：击杀 [0] 后原来的 [1] 会变成新的 [0]。批量斩杀时从高 index 往低打（先打 [1] 再打 [0]），或者一次只杀一个等下次轮询刷新状态
- 每次决策可以返回多个游戏操作，系统会按真人节奏逐个执行
- 如果使用 execute_actions，系统也会拆成逐步动作执行，先防御后攻击

【游戏基础知识】
- 每回合获得3点费用，出牌消耗费用，费用用完自动结束，部分牌和技能可以补充费用
- 击败所有敌人进入下一层，BOSS 在每关末尾
- 手牌中 "可出" 的牌可以打出，"需目标" 的牌要指定敌人编号
- 攻击牌造成伤害 → 优先打血量最低的敌人
- 防御牌获得格挡 → 敌人意图是ATTACK时优先出
- 主菜单时 start_game 开始新游戏，参考主播互动中观众的意见选择角色
- ★ 遇到【当前牌组/遗物】里没有效果描述、或者效果不清楚（如看不懂占位符 !D! / !B! / !M!）的牌，
  必须在决策前调用 get_card_info / get_relic_info 获取完整效果后再决策，不要瞎猜，再把相关信息写入important memory

{core_memory or '（暂无）'}

【当前牌组/遗物】
{important_memory or '（暂无）'}

【近期操作细节】
{recent_memory or '（暂无）'}

【游戏记忆系统】
{memory_section}

【解说与互动指导】★ 每次决策都应考虑 ★
{commentary_guide}

【操作历史】
{game_history or '（暂无操作）'}

【主播近期互动】
{host_history or '（暂无互动）'}

【当前游戏状态】
{game_state}

【返回格式】
每个 action 必须有 function.name 和 function.arguments。可以同时包含游戏操作和非游戏操作。

=== 可用操作类型 ===
1. 游戏操作：使用下方【可用MCP工具】列出的工具名
2. 主播互动：request_host_commentary（让主播解说），request_memory_update（更新记忆）

=== JSON 返回示例 ===

选择角色时：
{{"actions":[
  {{"function":{{"name":"request_host_commentary","arguments":{{"key_points":["开始新游戏","选了Wishdell_Mod"],"mood":"excited"}}}}}},
  {{"function":{{"name":"start_game","arguments":{{"class":"Wishdell_Mod"}}}}}}
]}}

注：start_game 成功后系统会**自动**从 MCP 拉取初始牌组/遗物（含具体数值与效果）并写入 important 记忆层，
你**不要**再调用 request_memory_update 写"5打击+4防御+1痛击，遗物：燃烧之血"这类固定模板，
初始信息由系统负责。

战斗中：
{{"actions":[
  {{"function":{{"name":"request_host_commentary","arguments":{{"key_points":["敌人要攻击了","我先叠甲保命"],"mood":"nervous"}}}}}},
  {{"function":{{"name":"execute_actions","arguments":{{"actions":[{{"action":"play_card","card_name":"防御","target_index":0}},{{"action":"play_card","card_name":"打击","target_index":1}},{{"action":"end_turn"}}]}}}}}}
]}}

拿新卡时：
{{"actions":[
  {{"function":{{"name":"request_host_commentary","arguments":{{"key_points":["拿到了旋风斩","配合双发会很厉害"],"mood":"happy"}}}}}},
  {{"function":{{"name":"request_memory_update","arguments":{{"memory_type":"important","mode":"search_replace","search":"牌组:","replace":"牌组:2旋风斩+1双发"}}}}}},
  {{"function":{{"name":"choose","arguments":{{"choice_index":0}}}}}}
]}}

请用上面的格式返回 JSON，不要加解释。"""

REQUEST_HOST_COMMENTARY_TOOL = {
    "type": "function",
    "function": {
        "name": "request_host_commentary",
        "description": "让主播进行解说，主播会以自己的风格表达这些要点",
        "parameters": {
            "type": "object",
            "properties": {
                "key_points": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "解说要点列表，主播会基于这些要点生成风格化解说",
                },
                "mood": {
                    "type": "string",
                    "description": "建议情绪: excited/confident/nervous/happy/sad/angry/neutral",
                },
            },
            "required": ["key_points"],
        },
    },
}

REQUEST_MEMORY_UPDATE_TOOL = {
    "type": "function",
    "function": {
        "name": "request_memory_update",
        "description": "更新游戏记忆系统。三层记忆: core(机制规律)、important(牌组遗物策略)、recent(近期战术要点)",
        "parameters": {
            "type": "object",
            "properties": {
                "memory_type": {
                    "type": "string",
                    "enum": ["core", "important", "recent"],
                    "description": "目标记忆层",
                },
                "mode": {
                    "type": "string",
                    "enum": ["rewrite", "search_replace"],
                    "description": "rewrite=完全重写该层(新内容替换旧内容), search_replace=搜索替换(修改记忆中的某一部分，适合小幅修正)",
                },
                "content": {
                    "type": "string",
                    "description": "rewrite模式: 替换该层全部内容; search_replace模式: 要替换成的目标内容",
                },
                "search": {
                    "type": "string",
                    "description": "search_replace模式时: 要替换掉的原文（用 mode内的内容替换掉这部分）",
                },
            },
            "required": ["memory_type", "mode", "content"],
        },
    },
}


@dataclass
class GameLoopState:
    game_state: Optional[UnifiedGameState] = None
    host_history_text: str = ""
    game_history_text: str = ""
    core_memory: str = ""
    important_memory: str = ""
    recent_memory: str = ""
    tools: list[dict] = field(default_factory=list)
    llm_response: Optional[str] = None
    tool_calls: list[dict] = field(default_factory=list)
    executed_actions: list[dict] = field(default_factory=list)
    commentary_requests: list[dict] = field(default_factory=list)
    memory_tool_calls: list[tuple[str, dict]] = field(default_factory=list)
    readonly_tool_calls: list[tuple[str, dict]] = field(default_factory=list)
    game_actions: list[tuple[str, dict]] = field(default_factory=list)
    _system_content: str = field(default="", init=False, repr=False)


class GameGraph:
    def __init__(
        self,
        adapter: BaseGameAdapter,
        shared_context: SharedContext | None = None,
        poll_interval: float | None = None,
        min_commentary_interval: float | None = None,
    ):
        self._adapter = adapter
        self._shared_context = shared_context or get_shared_context()
        self._poll_interval = poll_interval if poll_interval is not None else config.game_poll_interval
        self._min_commentary_interval = min_commentary_interval if min_commentary_interval is not None else config.game_min_commentary_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_decision_time: float = 0
        self._pending_game_actions: list[tuple[str, dict]] = []
        self._commentary = CommentaryCoordinator(
            shared_context=self._shared_context,
            game_id=self._adapter.game_id,
            min_interval=self._min_commentary_interval,
        )

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self):
        if self._running:
            logger.warning("游戏 Graph 已在运行")
            return

        healthy = await self._adapter.health_check()
        if not healthy:
            logger.warning(f"游戏 {self._adapter.game_id} MCP 服务不可用")
            return

        self._running = True
        self._task = asyncio.create_task(self._game_loop())
        logger.info(f"游戏 Graph 启动: {self._adapter.game_id}")

    async def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"游戏 Graph 停止: {self._adapter.game_id}")

    async def run_once(self) -> GameLoopState:
        state, _ = await self._run_state_machine_once()
        return state

    async def _run_state_machine_once(self) -> tuple[GameLoopState, bool]:
        state = GameLoopState()

        await self._node_collect_data(state)
        if not state.game_state:
            logger.warning("无法获取游戏状态")
            return state, False

        if not self._node_guard_turn(state):
            return state, False

        handled_game_over = await self._node_handle_game_over(state)
        if handled_game_over:
            return state, True

        screen = state.game_state.raw_state.get("screen_type", "") if state.game_state else ""
        if not screen:
            return state, False

        handled_pending = await self._node_execute_pending_action(state)
        if handled_pending:
            await self._node_update_history(state)
            return state, True

        await self._node_build_prompt(state)
        await self._node_llm_decide(state)
        self._node_route_tool_calls(state)
        had_game_action = await self._node_execute_tools(state)
        await self._node_update_history(state)
        return state, had_game_action

    async def _game_loop(self):
        while self._running:
            try:
                t_start = time.time()
                state, had_game_action = await self._run_state_machine_once()

                if not state.game_state or not self._adapter.is_my_turn(state.game_state):
                    await asyncio.sleep(self._poll_interval)
                    continue

                elapsed = time.time() - t_start
                if had_game_action:
                    min_wait = config.game_min_step_interval
                    jitter = random.uniform(-config.game_step_jitter, config.game_step_jitter)
                    min_wait = max(0.5, min_wait + jitter)
                else:
                    min_wait = self._poll_interval
                wait = max(min_wait - elapsed, 0)
                await asyncio.sleep(wait)

            except asyncio.CancelledError:
                break
            except (httpx.TimeoutException, httpx.ConnectError, ConnectionError, OSError) as e:
                logger.warning(f"游戏循环网络错误，将重试: {e}")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"游戏循环异常: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _node_collect_data(self, state: GameLoopState):
        await self._collect_data(state)

    def _node_guard_turn(self, state: GameLoopState) -> bool:
        if not state.game_state:
            return False
        if not self._adapter.is_my_turn(state.game_state):
            logger.info("不是我的回合")
            return False
        return True

    async def _node_handle_game_over(self, state: GameLoopState) -> bool:
        screen = state.game_state.raw_state.get("screen_type", "") if state.game_state else ""
        if screen != "GAME_OVER":
            return False
        logger.warning("游戏结束，尝试重启...")
        action = UnifiedAction(action_type="proceed", params={})
        await self._adapter.execute_action(action)
        await asyncio.sleep(1)
        action = UnifiedAction(action_type="start_game", params={"character": config.game_default_character})
        await self._adapter.execute_action(action)
        return True

    async def _node_execute_pending_action(self, state: GameLoopState) -> bool:
        if not self._pending_game_actions:
            return False
        name, params = self._pending_game_actions.pop(0)
        logger.info(f"执行缓冲动作: {name}({params})")
        await self._handle_game_action(name, params)
        return True

    async def _node_build_prompt(self, state: GameLoopState):
        await self._build_prompt(state)

    async def _node_llm_decide(self, state: GameLoopState):
        await self._llm_decide(state)

    def _node_route_tool_calls(self, state: GameLoopState):
        self._route_tool_calls(state)

    async def _node_execute_tools(self, state: GameLoopState) -> bool:
        return await self._execute_tools(state)

    async def _node_update_history(self, state: GameLoopState):
        await self._update_history(state)

    async def _collect_data(self, state: GameLoopState):
        try:
            results = await asyncio.gather(
                self._adapter.get_state(),
                self._shared_context.get_host_history_text(limit=5),
                self._shared_context.get_game_history_text(limit=12),
                return_exceptions=True,
            )

            state.game_state = results[0] if not isinstance(results[0], Exception) else None
            state.host_history_text = results[1] if not isinstance(results[1], Exception) else ""
            state.game_history_text = results[2] if not isinstance(results[2], Exception) else ""

            # 非阻塞节流同步：每 30s 最多一次将游戏状态写入知识图谱
            if state.game_state and hasattr(self._adapter, "ingest_game_state_to_graph"):
                now = time.time()
                if now - getattr(self, "_last_graph_sync", 0) >= 30:
                    self._last_graph_sync = now
                    asyncio.ensure_future(self._safe_graph_sync(state.game_state))

            # 从 MemoryEngine 获取记忆 (单局 + 长期 + 知识图谱)
            try:
                engine = get_memory_engine()
                memory_text = await engine.inject_for_game(game_id=self._adapter.game_id)
                if memory_text:
                    # 按 section 标记拆分为三层
                    core, important, recent = _split_memory_text(memory_text)
                    state.core_memory = core
                    state.important_memory = important
                    state.recent_memory = recent
                else:
                    state.core_memory = ""
                    state.important_memory = ""
                    state.recent_memory = ""
            except Exception as e:
                logger.warning(f"MemoryEngine 注入失败，回退 SharedContext: {e}")
                memory = await self._shared_context.get_memory()
                state.core_memory = memory.core
                state.important_memory = memory.important
                state.recent_memory = memory.recent

        except Exception as e:
            logger.error(f"数据收集失败: {e}")

    async def _safe_graph_sync(self, game_state):
        """包装图谱同步，确保异常不泄漏到事件循环"""
        try:
            await self._adapter.ingest_game_state_to_graph(game_state)
        except Exception as e:
            logger.debug(f"知识图谱同步跳过: {e}")

    async def _build_prompt(self, state: GameLoopState):
        raw = state.game_state.raw_state if state.game_state else {}
        game_state_text = self._adapter.format_state_for_prompt(raw, state.game_state.to_prompt_text() if state.game_state else "")

        state.tools = [REQUEST_HOST_COMMENTARY_TOOL, REQUEST_MEMORY_UPDATE_TOOL]
        state.tools.extend(get_memory_tools())  # memorize / recall
        try:
            mcp_tools = await self._adapter.get_tools_definition()
            state.tools.extend(mcp_tools)
        except Exception as e:
            logger.warning(f"获取 MCP tools 失败: {e}")

        mcp_tool_lines = []
        for t in state.tools:
            fn = t.get("function", {})
            name = fn.get("name", "")
            if name in ("request_host_commentary", "request_memory_update"):
                continue
            params = fn.get("parameters", {})
            props = params.get("properties", {})
            required = params.get("required", [])
            param_parts = []
            for pname, pinfo in props.items():
                desc = pinfo.get("description", "")
                if "enum" in pinfo:
                    desc = "/".join(pinfo["enum"])
                marker = "*" if pname in required else "?"
                param_parts.append(f"{marker}{pname}={desc}")
            tool_line = f"{name}: {', '.join(param_parts)}"
            mcp_tool_lines.append(tool_line)

        last_comm_time, last_comm_step = await self._shared_context.get_commentary_info()
        current_step = await self._shared_context.get_game_step_id()
        seconds_since_commentary = time.time() - last_comm_time if last_comm_time else float("inf")
        steps_since_commentary = current_step - last_comm_step if last_comm_time else 0

        system_content = build_game_system_prompt(
            core_memory=state.core_memory or "",
            important_memory=state.important_memory or "",
            recent_memory=state.recent_memory or "",
            game_history=state.game_history_text or "",
            host_history=state.host_history_text or "",
            game_state=game_state_text,
            seconds_since_commentary=seconds_since_commentary,
            steps_since_commentary=steps_since_commentary,
            commentary_interval=config.game_commentary_interval,
            min_step_interval=config.game_min_step_interval,
            memory_eagerness=config.game_memory_eagerness,
        )

        if mcp_tool_lines:
            system_content += "\n\n【可用MCP工具】\n" + "\n".join(mcp_tool_lines)

        state._system_content = system_content

    async def _llm_decide(self, state: GameLoopState):
        ai = get_game_ai_client()
        if not ai.available:
            logger.warning("AI 不可用，跳过游戏决策")
            return

        messages = [
            ChatMessage(role="system", content=state._system_content),
            ChatMessage(role="user", content="请返回JSON格式的决策，不要加任何解释。"),
        ]

        request = ChatRequest(
            messages=messages,
            model=config.game_model,
            temperature=config.game_temperature,
            max_tokens=config.game_max_tokens,
            tools=state.tools or None,
        )

        try:
            response = await ai.chat(request)
            if not response:
                logger.warning("游戏 LLM 响应为空")
                return

            if response.tool_calls:
                state.tool_calls = self._normalize_tool_calls(response.tool_calls) or []
                self._log_tool_calls(state.tool_calls)
                return

            if not response.content:
                logger.warning("游戏 LLM 响应为空")
                return

            state.llm_response = response.content
            self._parse_tool_calls(state)

        except Exception as e:
            logger.error(f"游戏 LLM 决策失败: {e}")

    def _parse_tool_calls(self, state: GameLoopState):
        content = state.llm_response
        if not content:
            return

        extracted = content
        import re

        md_match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
        if md_match:
            extracted = md_match.group(1).strip()

        try:
            parsed = json.loads(extracted)
        except json.JSONDecodeError:
            logger.debug(f"JSON解析失败: {extracted[:100]}")
            return

        normalized = self._normalize_tool_calls(parsed)
        if normalized:
            state.tool_calls = normalized
            self._log_tool_calls(normalized)
            return

        logger.debug(f"未检测到 tool_calls，原始响应: {content[:100]}")

    @staticmethod
    def _log_tool_calls(tool_calls: list[dict]):
        tool_names = [t.get("name", "?") for t in tool_calls]
        logger.info(f"LLM 决策: {tool_names}")
        for tc in tool_calls:
            name = tc.get("name", "?")
            params = tc.get("params", {})
            if params:
                logger.info(f"  └─ {name}: {params}")
            else:
                logger.info(f"  └─ {name}")

    @staticmethod
    def _normalize_tool_calls(data) -> list[dict] | None:
        items = None

        if isinstance(data, dict) and "actions" in data:
            items = data["actions"]
        elif isinstance(data, dict) and "tool_calls" in data:
            items = data["tool_calls"]
        elif isinstance(data, list):
            items = data

        if not items:
            return None

        result = []
        for item in items:
            if "function" in item:
                fn = item["function"]
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                result.append({"name": name, "params": args})
            elif "action" in item:
                params = {k: v for k, v in item.items() if k != "action"}
                result.append({"name": item["action"], "params": params})
            elif "name" in item:
                result.append(item)

        return result if result else None

    def _route_tool_calls(self, state: GameLoopState):
        state.commentary_requests.clear()
        state.memory_tool_calls.clear()
        state.readonly_tool_calls.clear()
        state.game_actions.clear()

        for tc in state.tool_calls:
            name = tc.get("name", tc.get("function", {}).get("name", ""))
            params = tc.get("params", tc.get("arguments", tc.get("function", {}).get("arguments", {})))
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    params = {}

            if name == "request_host_commentary":
                state.commentary_requests.append(params if isinstance(params, dict) else {})
            elif name in {"request_memory_update", "memorize", "recall"}:
                state.memory_tool_calls.append((name, params if isinstance(params, dict) else {}))
            elif name in READONLY_MCP_TOOLS:
                state.readonly_tool_calls.append((name, params if isinstance(params, dict) else {}))
            elif name:
                state.game_actions.extend(self._expand_game_action(name, params if isinstance(params, dict) else {}))

    @staticmethod
    def _expand_game_action(name: str, params: dict) -> list[tuple[str, dict]]:
        """把批量游戏动作拆成单步动作，让 GameGraph 的速率限制逐步生效。"""
        if name != "execute_actions":
            return [(name, params)]

        actions = params.get("actions", [])
        if not isinstance(actions, list) or not actions:
            return [(name, params)]

        expanded: list[tuple[str, dict]] = []
        for item in actions:
            if not isinstance(item, dict):
                continue
            action_name = item.get("action") or item.get("name")
            if not action_name:
                continue
            action_params = {k: v for k, v in item.items() if k not in {"action", "name"}}
            expanded.append((str(action_name), action_params))
        return expanded or [(name, params)]

    async def _execute_tools(self, state: GameLoopState) -> bool:
        if not state.tool_calls:
            return False

        await self._execute_memory_tools(state)
        await self._execute_readonly_tools(state)

        commentary_ack = None
        if state.commentary_requests:
            commentary_ack = await self._commentary.enqueue_and_wait(
                state.commentary_requests,
                timeout=config.game_commentary_hold_timeout,
            )
            if commentary_ack:
                logger.info(
                    "解说处理完成: id=%s status=%s",
                    commentary_ack.request_id,
                    commentary_ack.status,
                )

        if state.game_actions:
            if commentary_ack and commentary_ack.status not in {"spoken", "llm_failed", "failed", "timeout", "dropped", "cancelled"}:
                logger.debug("解说状态未终结，仍继续执行游戏动作: %s", commentary_ack.status)
            await self._execute_game_actions(state.game_actions)
            return True

        return commentary_ack is not None

    async def _execute_memory_tools(self, state: GameLoopState):
        tasks = []
        for name, params in state.memory_tool_calls:
            if name == "request_memory_update":
                tasks.append(self._handle_memory_update_request(params))
            elif name in ("memorize", "recall"):
                tasks.append(handle_memory_tool_call(name, params, game_id=self._adapter.game_id))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning("记忆工具执行失败: %s", result)

    async def _execute_readonly_tools(self, state: GameLoopState):
        if not state.readonly_tool_calls:
            return
        results = await asyncio.gather(
            *(self._handle_mcp_readonly(name, params) for name, params in state.readonly_tool_calls),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning("MCP只读工具执行失败: %s", result)

    async def _execute_game_actions(self, game_actions: list[tuple[str, dict]]):
        name, params = game_actions[0]
        await self._handle_game_action(name, params)
        remaining = game_actions[1:]
        if remaining:
            self._pending_game_actions = remaining
            logger.info(f"剩余动作缓冲: {[a[0] for a in remaining]}")

    async def _handle_memory_update_request(self, params: dict):
        memory_type = params.get("memory_type", "")
        mode = params.get("mode", "rewrite")
        content = params.get("content", "") or params.get("replace", "")
        if not memory_type or not content:
            logger.warning("记忆更新参数不完整")
            return False

        # 同步到 MemoryEngine 的 SessionMemory
        engine = get_memory_engine()
        session = engine.session

        if mode == "rewrite":
            if memory_type == "core":
                session.update_core(content)
            elif memory_type == "important":
                session.update_important(content)
            elif memory_type == "recent":
                session.update_recent(content)
            logger.info(f"LLM 重写 {memory_type} 记忆: {content[:50]}...")
        elif mode == "search_replace":
            search = params.get("search", "")
            if search:
                session.search_replace(memory_type, search, content)
                logger.info(f"LLM 搜索替换 {memory_type}: '{search[:30]}' -> '{content[:30]}'")
            else:
                logger.warning("search_replace 模式缺少 search 参数")
                return False

        # 同时写入 SharedContext 保持兼容
        await self._shared_context.rewrite_memory(memory_type=memory_type, content=content if mode == "rewrite" else session.core if memory_type == "core" else session.important if memory_type == "important" else session.recent)
        await self._shared_context.add_game_entry(
            action="request_memory_update",
            params={"memory_type": memory_type, "mode": mode, "content": content[:100]},
            result="updated",
        )
        return True

    async def _handle_mcp_readonly(self, name: str, params: dict):
        try:
            data = await self._adapter.query_tool(name, params if isinstance(params, dict) else {})
            preview = str(data)[:300]
            await self._shared_context.add_game_entry(
                action=name,
                params=params if isinstance(params, dict) else {},
                result=f"query: {preview}",
            )
            logger.debug(f"MCP只读查询: {name} -> {preview}")
            return data
        except Exception as e:
            logger.warning(f"MCP只读查询失败: {name} -> {e}")
            await self._shared_context.add_game_entry(
                action=name,
                params=params if isinstance(params, dict) else {},
                result=f"failed: {e}",
            )
            return None

    async def _handle_game_action(self, name: str, params: dict):
        action = UnifiedAction(
            action_type=name,
            params=params if isinstance(params, dict) else {},
        )
        success, error_msg = await self._adapter.execute_action(action)
        result = f"success: {error_msg}" if success else f"failed: {error_msg}"

        if name == "start_game" and success:
            await self._shared_context.clear_all_memory()
            # 清空 MemoryEngine 单局记忆
            engine = get_memory_engine()
            engine.start_new_game()

            # 通用钩子：让 adapter 在开局后做游戏特定的副作用
            # （例如杀戮尖塔会从 MCP 拉初始牌组/遗物写入 important 记忆）
            try:
                async def write_important(text: str) -> None:
                    await self._shared_context.rewrite_memory("important", text)
                    if hasattr(engine, "session") and hasattr(engine.session, "update_important"):
                        engine.session.update_important(text)

                await self._adapter.on_game_started(write_important)
            except Exception as e:
                logger.warning(f"adapter.on_game_started 失败: {e}")
        else:
            engine = get_memory_engine()
            engine.record_game_event(
                event_type="game_action",
                content=f"{name}({params}) -> {result}",
                metadata={"action": name, "success": success},
            )
            if success:
                await engine.summarize_session_if_needed()

        await self._shared_context.add_game_entry(
            action=name,
            params=params if isinstance(params, dict) else {},
            result=result,
        )
        if success:
            await self._shared_context.advance_game_step()
        logger.info(f"游戏动作执行: {name} -> {result}")
        return success

    async def _update_history(self, state: GameLoopState):
        self._last_decision_time = time.time()
