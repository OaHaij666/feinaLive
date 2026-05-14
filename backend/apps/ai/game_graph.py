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

from apps.ai.client import ChatMessage, ChatRequest, get_game_ai_client
from apps.ai.mcp.base_adapter import BaseGameAdapter, UnifiedAction, UnifiedGameState
from apps.ai.messaging.queue import PRIORITY_HIGH, Message, get_message_queue
from apps.ai.shared_context import SharedContext, get_shared_context
from apps.config import config

logger = logging.getLogger(__name__)

NON_GAME_TOOLS = {"request_host_commentary", "request_memory_update"}

READONLY_MCP_TOOLS = {
    "get_game_state", "get_screen_state", "get_available_commands",
    "get_card_info", "get_relic_info", "get_potion_info",
}


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
- 敌人意图为 ATTACK 时，**必须先出防御牌叠格挡**，格挡量 >= 敌人预计伤害才能结束回合
- 只有在敌人无攻击意图（正在BUFF/DEBUFF/准备技能）时才全力输出
- 3费回合：优先出1-2张防御牌保命，剩余费用打输出，不要把所有费都用来攻击
- execute_actions 可以一次执行多个动作（含 end_turn），先防御后攻击

【游戏基础知识】
- 每回合获得3点费用，出牌消耗费用，费用用完自动结束，部分牌和技能可以补充费用
- 击败所有敌人进入下一层，BOSS 在每关末尾
- 手牌中 "可出" 的牌可以打出，"需目标" 的牌要指定敌人编号
- 攻击牌造成伤害 → 优先打血量最低的敌人
- 防御牌获得格挡 → 敌人意图是ATTACK时优先出
- 主菜单时 start_game 开始新游戏，参考主播互动中观众的意见选择角色

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
  {{"function":{{"name":"request_host_commentary","arguments":{{"key_points":["开始新游戏","选了铁甲战士"],"mood":"excited"}}}}}},
  {{"function":{{"name":"request_memory_update","arguments":{{"memory_type":"important","mode":"rewrite","content":"初始牌组：5打击+4防御+1痛击，遗物：燃烧之血"}}}}}},
  {{"function":{{"name":"choose","arguments":{{"choice_index":1}}}}}}
]}}

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
        state = GameLoopState()

        await self._collect_data(state)
        if not state.game_state:
            logger.warning("无法获取游戏状态")
            return state

        if not self._adapter.is_my_turn(state.game_state):
            logger.info("不是我的回合")
            return state

        screen = state.game_state.raw_state.get("screen_type", "") if state.game_state else ""
        if screen == "GAME_OVER":
            logger.warning("游戏结束，尝试重启...")
            action = UnifiedAction(action_type="proceed", params={})
            await self._adapter.execute_action(action)
            await asyncio.sleep(1)
            action = UnifiedAction(action_type="start_game", params={"character": config.game_default_character})
            await self._adapter.execute_action(action)
            return state

        if not screen:
            return state

        if self._pending_game_actions:
            name, params = self._pending_game_actions.pop(0)
            logger.info(f"执行缓冲动作: {name}({params})")
            await self._handle_game_action(name, params)
        else:
            await self._build_prompt(state)
            await self._llm_decide(state)
            await self._execute_parallel(state)

        await self._update_history(state)

        return state

    async def _game_loop(self):
        while self._running:
            try:
                t_start = time.time()
                state = GameLoopState()

                await self._collect_data(state)
                if not state.game_state:
                    await asyncio.sleep(self._poll_interval)
                    continue

                if not self._adapter.is_my_turn(state.game_state):
                    await asyncio.sleep(self._poll_interval)
                    continue

                screen = state.game_state.raw_state.get("screen_type", "") if state.game_state else ""
                if screen == "GAME_OVER":
                    logger.warning("游戏结束，尝试重启...")
                    action = UnifiedAction(action_type="proceed", params={})
                    await self._adapter.execute_action(action)
                    await asyncio.sleep(1)
                    action = UnifiedAction(action_type="start_game", params={"character": config.game_default_character})
                    await self._adapter.execute_action(action)
                    await asyncio.sleep(3)
                    continue

                if not screen:
                    await asyncio.sleep(self._poll_interval)
                    continue

                if self._pending_game_actions:
                    name, params = self._pending_game_actions.pop(0)
                    logger.info(f"执行缓冲动作: {name}({params})")
                    await self._handle_game_action(name, params)
                    had_game_action = True
                else:
                    await self._build_prompt(state)
                    await self._llm_decide(state)
                    had_game_action = await self._execute_parallel(state)

                await self._update_history(state)

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
            except Exception as e:
                logger.error(f"游戏循环异常: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _collect_data(self, state: GameLoopState):
        try:
            results = await asyncio.gather(
                self._adapter.get_state(),
                self._shared_context.get_host_history_text(limit=5),
                self._shared_context.get_game_history_text(limit=12),
                self._shared_context.get_memory(),
                return_exceptions=True,
            )

            state.game_state = results[0] if not isinstance(results[0], Exception) else None
            state.host_history_text = results[1] if not isinstance(results[1], Exception) else ""
            state.game_history_text = results[2] if not isinstance(results[2], Exception) else ""
            memory = results[3] if not isinstance(results[3], Exception) else None
            if memory and hasattr(memory, "core"):
                state.core_memory = memory.core
                state.important_memory = memory.important
                state.recent_memory = memory.recent
            else:
                state.core_memory = ""
                state.important_memory = ""
                state.recent_memory = ""

        except Exception as e:
            logger.error(f"数据收集失败: {e}")

    async def _build_prompt(self, state: GameLoopState):
        raw = state.game_state.raw_state if state.game_state else {}
        game_state_text = self._adapter.format_state_for_prompt(raw, state.game_state.to_prompt_text() if state.game_state else "")

        state.tools = [REQUEST_HOST_COMMENTARY_TOOL, REQUEST_MEMORY_UPDATE_TOOL]
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
        )

        try:
            response = await ai.chat(request)
            if not response or not response.content:
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
            tool_names = [t.get("name", "?") for t in normalized]
            logger.info(f"LLM 决策: {tool_names}")
            for tc in normalized:
                name = tc.get("name", "?")
                params = tc.get("params", {})
                if params:
                    logger.info(f"  └─ {name}: {params}")
                else:
                    logger.info(f"  └─ {name}")
            return

        logger.debug(f"未检测到 tool_calls，原始响应: {content[:100]}")

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

    async def _execute_parallel(self, state: GameLoopState) -> bool:
        if not state.tool_calls:
            return False

        non_game_tasks = []
        game_actions = []
        commentary_params = None

        for tc in state.tool_calls:
            name = tc.get("name", tc.get("function", {}).get("name", ""))
            params = tc.get("params", tc.get("arguments", tc.get("function", {}).get("arguments", {})))

            if name == "request_host_commentary":
                commentary_params = params
            elif name == "request_memory_update":
                non_game_tasks.append(self._handle_memory_update_request(params))
            elif name in READONLY_MCP_TOOLS:
                non_game_tasks.append(self._handle_mcp_readonly(name, params))
            elif name:
                game_actions.append((name, params))

        if non_game_tasks:
            await asyncio.gather(*non_game_tasks, return_exceptions=True)

        commentary_enqueued = False
        if commentary_params is not None:
            commentary_enqueued = await self._handle_commentary_request(commentary_params)

        if commentary_enqueued and game_actions:
            logger.info(f"解说已入队，暂扣 {len(game_actions)} 个游戏动作等待消费...")
            consumed = await self._shared_context.wait_commentary_consumed(
                timeout=config.game_commentary_hold_timeout
            )
            if consumed:
                logger.info("解说已消费，释放游戏动作")
            else:
                logger.info(f"解说等消费超时 (>{config.game_commentary_hold_timeout}s)，跳过解说执行游戏动作")

        if game_actions:
            name, params = game_actions[0]
            await self._handle_game_action(name, params)
            remaining = game_actions[1:]
            if remaining:
                self._pending_game_actions = remaining
                logger.info(f"剩余动作缓冲: {[a[0] for a in remaining]}")
            return True

        return commentary_enqueued

    async def _handle_commentary_request(self, params: dict) -> bool:
        """解说请求入队。返回 True 表示已入队。

        使用 SharedContext 的 _last_commentary_time（只有真正消费才更新）做间隔检查。
        不再更新本地或 SharedContext 的时间戳——留给 HostGraph 消费后更新。
        """
        now = time.time()
        last_consumed = await self._shared_context.get_last_commentary_time()
        if now - last_consumed < self._min_commentary_interval:
            logger.debug(
                f"距上次成功解说仅 {now - last_consumed:.1f}s，"
                f"小于硬间隔 {self._min_commentary_interval}s，跳过"
            )
            return False

        hold_timeout = config.game_commentary_hold_timeout
        cancel_key = f"commentary_{self._adapter.game_id}_{int(now)}"
        game_step_id = await self._shared_context.get_game_step_id()
        queue = get_message_queue()
        msg = Message(
            priority=PRIORITY_HIGH,
            source="game",
            msg_type="commentary_request",
            content=" | ".join(params.get("key_points", [])),
            data={
                "key_points": params.get("key_points", []),
                "mood": params.get("mood", "neutral"),
                "game_step_id": game_step_id,
            },
            cancel_key=cancel_key,
            expire_at=now + hold_timeout + 5,
            allow_skip=False,
        )
        success = await queue.put(msg)
        if success:
            await self._shared_context.record_commentary_request()
            key_points = params.get("key_points", [])
            mood = params.get("mood", "neutral")
            logger.info(f"解说请求入队: {key_points} (step={game_step_id})")
            await self._shared_context.add_game_entry(
                action="request_host_commentary",
                params={"key_points": key_points, "mood": mood},
                result="enqueued",
            )
        return success

    async def _handle_memory_update_request(self, params: dict):
        memory_type = params.get("memory_type", "")
        mode = params.get("mode", "rewrite")
        content = params.get("content", "") or params.get("replace", "")
        if not memory_type or not content:
            logger.warning("记忆更新参数不完整")
            return False

        if mode == "rewrite":
            await self._shared_context.rewrite_memory(memory_type=memory_type, content=content)
            logger.info(f"LLM 重写 {memory_type} 记忆: {content[:50]}...")
            await self._shared_context.add_game_entry(
                action="request_memory_update",
                params={"memory_type": memory_type, "mode": "rewrite", "content": content[:100]},
                result="rewritten",
            )
        elif mode == "search_replace":
            search = params.get("search", "")
            if search:
                await self._shared_context.search_replace_memory(
                    memory_type=memory_type, mode="fuzzy", search=search, replace=content
                )
                logger.info(f"LLM 搜索替换 {memory_type}: '{search[:30]}' -> '{content[:30]}'")
                await self._shared_context.add_game_entry(
                    action="request_memory_update",
                    params={"memory_type": memory_type, "mode": "search_replace", "search": search[:50], "replace": content[:50]},
                    result="replaced",
                )
            else:
                logger.warning("search_replace 模式缺少 search 参数")
                return False
        return True

    async def _handle_mcp_readonly(self, name: str, params: dict):
        success, error_msg = await self._adapter.execute_action(
            UnifiedAction(action_type=name, params=params if isinstance(params, dict) else {})
        )
        logger.debug(f"MCP只读查询: {name} -> {'ok' if success else error_msg}")
        return success

    async def _handle_game_action(self, name: str, params: dict):
        action = UnifiedAction(
            action_type=name,
            params=params if isinstance(params, dict) else {},
        )
        success, error_msg = await self._adapter.execute_action(action)
        result = f"success: {error_msg}" if success else f"failed: {error_msg}"

        if name == "start_game" and success:
            await self._shared_context.clear_all_memory()

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
