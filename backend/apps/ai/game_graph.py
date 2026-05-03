"""游戏 Graph - MCP 游戏决策主循环

流程:
1. 数据收集 (并行): MCP游戏状态 + 主播历史 + 游戏历史 + 总记忆
2. 构建提示词: 组合所有上下文 + MCP tools + 内置tool
3. LLM 决策: 生成 tool_calls
4. 并发执行: MCP工具立即执行, request_host_commentary 放入消息队列
5. 更新历史: 记录本次操作
6. 进入下一轮
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from apps.ai.client import ChatMessage, ChatRequest, get_game_ai_client
from apps.ai.mcp.base_adapter import BaseGameAdapter, UnifiedAction, UnifiedGameState
from apps.ai.messaging.queue import PRIORITY_HIGH, Message, get_message_queue
from apps.ai.shared_context import SharedContext, get_shared_context
from apps.config import config

logger = logging.getLogger(__name__)


def _commentary_prompt(eagerness: int) -> str:
    if eagerness <= 1:
        return "- 只在极端情况（BOSS战、即将死亡）时调用 request_host_commentary 让主播解说"
    elif eagerness <= 2:
        return "- 残血、精英战、BOSS战时调用 request_host_commentary 让主播解说\n- 例如\"观众们小心，铁甲战士只剩10点血了\""
    elif eagerness <= 3:
        return "- 战斗有趣或有挑战时调用 request_host_commentary 让主播解说\n- 拿到好卡/遗物时也值得解说，如\"我拿到了死灵之书，配合重锤会很厉害！\""
    elif eagerness <= 4:
        return (
            "- 经常调用 request_host_commentary 让主播解说，像游戏主播一样保持直播活跃\n"
            "- 遇到以下情况时主动解说:\n"
            "  打出一套漂亮连招时 → \"观众们看好了，旋风斩配合双发清场！\"\n"
            "  获得新卡/遗物时 → \"这个遗物正好配合我的牌组\"\n"
            "  遭遇精英/Boss时 → \"前方高能，遇到精英怪了！\"\n"
            "  战术发生变化时 → \"我决定这局走攻击路线\"\n"
            "  状况危急或大获全胜时 → 分享兴奋或担忧\n"
            "  事件触发时 → \"涅奥给了我一个祝福，选哪个好呢\"\n"
            "- key_points 列出解说要点，主播会用自己的风格表达\n"
            "- mood 可以选 excited/confident/nervous/happy/neutral\n"
            "- reference_danmaku 可以引用观众弹幕互动，如观众说\"选观者\"时可以回应\n"
            "- 每层至少解说 1-2 次"
        )
    else:
        return "- 积极调用 request_host_commentary 让主播解说，像真正的游戏主播一样\n- 每回合都可以说几句，点评局面、吐槽敌人、分享策略\n- 拿到新卡、击杀精英、遭遇事件时都要解说\n- 不要错过任何展示主播魅力的机会"


def _memory_prompt(eagerness: int) -> str:
    base = "调用 request_memory_update 把重要信息写入记忆，mode=rewrite 完全重写，mode=search_replace 搜索替换。\n"
    base += "三层记忆在下次决策时可见:\n"
    base += "- core=游戏机制规律发现 → 如\"AOE牌清场效率高\"\n"
    base += "- important=当前牌组/遗物评估 → 如\"牌组:2旋风斩+双发;遗物:燃烧之血\"\n"
    base += "- recent=近期战术路线 → 如\"选择了偏攻击路线\"\n"

    if eagerness <= 1:
        base += "\n只在发现重大机制规律时 rewrite core，极少调用。"
    elif eagerness <= 2:
        base += "\n拿到新卡/遗物后 rewrite important，发现机制规律时 rewrite core。"
    elif eagerness <= 3:
        base += "- 拿到新卡/遗物后 rewrite important，写简洁评估如\"牌组:5打击4防御1痛击;遗物:燃烧之血+新遗物\"\n"
        base += "- 牌组小幅变化用 search_replace 修正 important，如 search=\"5打击\" content=\"4打击+1完美打击\"\n"
        base += "- 战术路线变化 rewrite recent，如\"拿到旋风斩后转向AOE清场路线\"\n"
        base += "- 发现机制规律 rewrite core，如\"痛击对残血敌人溢出伤害高\"\n"
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
    commentary_eagerness: int = 3,
    memory_eagerness: int = 3,
) -> str:
    commentary_rule = _commentary_prompt(commentary_eagerness)
    memory_section = _memory_prompt(memory_eagerness)

    return f"""你是杀戮尖塔游戏策略AI，控制主播玩游戏并与观众互动。

【战斗核心原则】★★★ 最重要 ★★★
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

【决策规则】
- 优先使用 execute_actions 批量出牌 + end_turn
{commentary_rule}

【操作历史】
{game_history or '（暂无操作）'}

【主播近期互动】
{host_history or '（暂无互动）'}

【当前游戏状态】
{game_state}

请用 JSON 格式返回你的决策，不要加解释文字:
例子:
  战斗中: {{"actions":[{{"action":"execute_actions","actions":[{{"action":"play_card","card_name":"打击","target_index":1}},{{"action":"end_turn"}}]}}]}}
  选择时: {{"actions":[{{"action":"choose","choice_index":1}},{{"action":"proceed"}}]}}"""

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
                "reference_danmaku": {
                    "type": "string",
                    "description": "可参考的弹幕内容，用于回应观众",
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
        poll_interval: float = 1.0,
        min_commentary_interval: float = 15.0,
    ):
        self._adapter = adapter
        self._shared_context = shared_context or get_shared_context()
        self._poll_interval = poll_interval
        self._min_commentary_interval = min_commentary_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_decision_time: float = 0
        self._last_commentary_time: float = 0

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
            action = UnifiedAction(action_type="start_game", params={"character": "IRONCLAD"})
            await self._adapter.execute_action(action)
            return state

        if not screen:
            return state

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
                    action = UnifiedAction(action_type="start_game", params={"character": "IRONCLAD"})
                    await self._adapter.execute_action(action)
                    await asyncio.sleep(3)
                    continue

                if not screen:
                    await asyncio.sleep(self._poll_interval)
                    continue

                await self._build_prompt(state)
                await self._llm_decide(state)
                await self._execute_parallel(state)
                await self._update_history(state)

                elapsed = time.time() - t_start
                min_wait = config.game_min_step_interval
                wait = max(min_wait - elapsed, self._poll_interval)
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

    @staticmethod
    def _format_game_state(raw: dict, fallback: str) -> str:
        lines = []
        screen = raw.get("screen_type", "?")
        floor = raw.get("floor", "?")
        hp = raw.get("current_hp", "?")
        max_hp = raw.get("max_hp", "?")

        lines.append(f"画面: {screen} | 楼层: {floor}")
        lines.append(f"HP: {hp}/{max_hp}")

        combat = raw.get("combat_state", {})
        player_combat = combat.get("player", {})
        energy = player_combat.get("current_energy", raw.get("current_energy", raw.get("energy")))
        if energy is not None:
            lines.append(f"费用: {energy}")

        monsters = combat.get("monsters", raw.get("monsters", []))
        if monsters:
            lines.append("敌人:")
            for i, m in enumerate(monsters, 1):
                if m.get("is_gone"):
                    continue
                intent = m.get("intent", "?")
                move = m.get("move", {})
                damage = move.get("damage") if move else None
                hits = move.get("hits", "") if move else ""
                intent_detail = intent
                if damage:
                    intent_detail += f" {damage}"
                    if hits and hits > 1:
                        intent_detail += f"x{hits}"
                block = m.get("block", 0)
                block_str = f" [格挡{block}]" if block else ""
                lines.append(f"  [{i}] {m.get('name')} HP:{m.get('current_hp')}/{m.get('max_hp')} 意图:{intent_detail}{block_str}")

        hand = combat.get("hand", raw.get("hand", []))
        if hand:
            lines.append("手牌:")
            for i, c in enumerate(hand, 1):
                playable = "可出" if c.get("is_playable") else "不可出"
                target = " 需目标" if c.get("has_target") else ""
                lines.append(f"  {i}. {c.get('name')} 费{c.get('cost')} {playable}{target}")

        choices = raw.get("choice_list", [])
        if choices:
            lines.append("选项:")
            for i, ch in enumerate(choices, 1):
                lines.append(f"  {i}. {ch}")

        return "\n".join(lines)

    async def _build_prompt(self, state: GameLoopState):
        raw = state.game_state.raw_state if state.game_state else {}
        game_state_text = self._format_game_state(raw, state.game_state.to_prompt_text() if state.game_state else "")

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

        system_content = build_game_system_prompt(
            core_memory=state.core_memory or "",
            important_memory=state.important_memory or "",
            recent_memory=state.recent_memory or "",
            game_history=state.game_history_text or "",
            host_history=state.host_history_text or "",
            game_state=game_state_text,
            commentary_eagerness=config.game_commentary_eagerness,
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

    async def _execute_parallel(self, state: GameLoopState):
        if not state.tool_calls:
            return

        tasks = []
        for tc in state.tool_calls:
            name = tc.get("name", tc.get("function", {}).get("name", ""))
            params = tc.get("params", tc.get("arguments", tc.get("function", {}).get("arguments", {})))

            if name == "request_host_commentary":
                tasks.append(self._handle_commentary_request(params))
            elif name == "request_memory_update":
                tasks.append(self._handle_memory_update_request(params))
            elif name:
                tasks.append(self._handle_game_action(name, params))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _handle_commentary_request(self, params: dict):
        now = time.time()
        if now - self._last_commentary_time < self._min_commentary_interval:
            logger.debug(f"解说请求间隔过短，跳过 (距上次 {now - self._last_commentary_time:.1f}s)")
            return False

        cancel_key = f"commentary_{self._adapter.game_id}_{int(now)}"
        queue = get_message_queue()
        msg = Message(
            priority=PRIORITY_HIGH,
            source="game",
            msg_type="commentary_request",
            content=" | ".join(params.get("key_points", [])),
            data={
                "key_points": params.get("key_points", []),
                "mood": params.get("mood", "neutral"),
                "reference_danmaku": params.get("reference_danmaku", ""),
            },
            cancel_key=cancel_key,
            expire_at=time.time() + 10,
            allow_skip=False,
        )
        success = await queue.put(msg)
        if success:
            self._last_commentary_time = now
            logger.info(f"解说请求入队: {params.get('key_points', [])}")
        return success

    async def _handle_memory_update_request(self, params: dict):
        memory_type = params.get("memory_type", "")
        mode = params.get("mode", "rewrite")
        content = params.get("content", "")
        if not memory_type or not content:
            logger.warning("记忆更新参数不完整")
            return False

        if mode == "rewrite":
            await self._shared_context.rewrite_memory(memory_type=memory_type, content=content)
            logger.info(f"LLM 重写 {memory_type} 记忆: {content[:50]}...")
        elif mode == "search_replace":
            search = params.get("search", "")
            if search:
                await self._shared_context.search_replace_memory(
                    memory_type=memory_type, mode="fuzzy", search=search, replace=content
                )
                logger.info(f"LLM 搜索替换 {memory_type}: '{search[:30]}' -> '{content[:30]}'")
            else:
                logger.warning("search_replace 模式缺少 search 参数")
                return False
        return True

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
        logger.info(f"游戏动作执行: {name} -> {result}")
        return success

    async def _update_history(self, state: GameLoopState):
        self._last_decision_time = time.time()
