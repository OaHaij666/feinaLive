"""主播 Graph - 消费消息队列，主播 LLM 统一生成话术 → TTS 输出

所有消息由主播 LLM 统一消费，TTS 只是最后把话转语音的工具步骤。

消费的消息类型:
  - commentary_request  GameGraph 请求游戏解说(带草稿要点) → 主播 LLM 风格化 → TTS
  - danmaku             观众弹幕原文 → 主播 LLM 生成回复 → TTS
  - gift_thanks         礼物感谢 → 主播 LLM 生成感谢语 → TTS

流程:
1. 阻塞等待消息队列
2. 按 msg_type 构建对应的提示词
3. 主播 LLM 生成话术
4. TTS 合成播放
5. 写入 SharedContext (让 GameGraph 感知主播说了什么)
"""

import asyncio
import logging
import time
from typing import Callable

from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
from apps.ai.messaging.queue import Message, get_message_queue
from apps.ai.prompt import get_host_system_prompt
from apps.ai.shared_context import get_shared_context
from apps.ai.tts import get_tts_client
from apps.config import config

logger = logging.getLogger(__name__)

COMMENTARY_SYSTEM_PROMPT = """{host_personality}

【解说要点】
{key_points}

【建议情绪】
{mood}

【你刚才的互动】
{host_history}

【可参考弹幕】
{reference_danmaku}

请根据以上要点生成一段风格化解说:
- 用第一人称
- 口语化、自然
- 可以加入口癖和情感词
- 长度控制在 20-50 字
- 不要重复要点原文，用自己的风格重新表达"""

DANMAKU_REPLY_PROMPT = """{host_personality}

【观众说】
{danmaku}

【你刚才的互动】
{host_history}

请回复这条弹幕:
- 用第一人称
- 口语化、自然
- 可以加入口癖和情感词
- 长度控制在 20-50 字"""

GIFT_THANKS_PROMPT = """{host_personality}

【你刚才的互动】
{host_history}

观众送了礼物: {gift_info}

请生成一段感谢语:
- 用第一人称
- 口语化、自然
- 长度控制在 15-30 字
- 感谢要真诚不油腻"""


class HostGraph:
    def __init__(
        self,
        on_reply: Callable[[str], asyncio.coroutine] | None = None,
    ):
        self._shared_context = get_shared_context()
        self._running = False
        self._task: asyncio.Task | None = None
        self._on_reply = on_reply
        self._last_tts_time: float = 0

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self):
        if self._running:
            logger.warning("主播 Graph 已在运行")
            return

        self._running = True
        self._task = asyncio.create_task(self._host_loop())
        logger.info("主播 Graph 启动")

    async def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("主播 Graph 停止")

    async def _host_loop(self):
        queue = get_message_queue()

        while self._running:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=5.0)

                if msg.msg_type == "commentary_request":
                    await self._handle_commentary(msg)
                elif msg.msg_type == "danmaku":
                    await self._handle_danmaku(msg)
                elif msg.msg_type == "gift_thanks":
                    await self._handle_gift_thanks(msg)
                else:
                    logger.warning(f"未知消息类型: {msg.msg_type}")

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"主播循环异常: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _handle_commentary(self, msg: Message):
        data = msg.data
        key_points = data.get("key_points", [])
        mood = data.get("mood", "neutral")
        reference_danmaku = data.get("reference_danmaku", "")

        host_personality = get_host_system_prompt()
        host_history = await self._shared_context.get_host_history_text(limit=10)

        system_content = COMMENTARY_SYSTEM_PROMPT.format(
            host_personality=host_personality,
            key_points="\n".join(f"- {p}" for p in key_points),
            mood=mood,
            host_history=host_history or "（暂无）",
            reference_danmaku=reference_danmaku or "无",
        )

        spoken = await self._llm_generate(system_content, "请生成解说。", config.host_max_tokens)
        if not spoken:
            return

        logger.info(f"主播解说: {spoken}")
        await self._speak(spoken)

        await self._shared_context.add_host_entry(
            danmaku=reference_danmaku or f"[游戏解说-{mood}]",
            reply=spoken,
        )

        if self._on_reply:
            await self._on_reply(spoken)

    async def _handle_danmaku(self, msg: Message):
        danmaku = msg.content
        user = msg.data.get("user", "unknown")

        host_personality = get_host_system_prompt()
        host_history = await self._shared_context.get_host_history_text(limit=10)

        system_content = DANMAKU_REPLY_PROMPT.format(
            host_personality=host_personality,
            danmaku=danmaku,
            host_history=host_history or "（暂无）",
        )

        spoken = await self._llm_generate(system_content, "请回复弹幕。", config.host_max_tokens)
        if not spoken:
            return

        logger.info(f"主播回复弹幕 [{user}]: {spoken[:30]}...")
        await self._speak(spoken)

        await self._shared_context.add_host_entry(
            danmaku=danmaku,
            reply=spoken,
            user=user,
        )

        if self._on_reply:
            await self._on_reply(spoken)

    async def _handle_gift_thanks(self, msg: Message):
        data = msg.data
        gift_info = data.get("gift_info", msg.content)
        user = data.get("user", "")

        host_personality = get_host_system_prompt()
        host_history = await self._shared_context.get_host_history_text(limit=5)

        system_content = GIFT_THANKS_PROMPT.format(
            host_personality=host_personality,
            host_history=host_history or "（暂无）",
            gift_info=gift_info,
        )

        spoken = await self._llm_generate(system_content, "请生成感谢语。", 80)
        if not spoken:
            return

        logger.info(f"礼物感谢: {spoken}")
        await self._speak(spoken)

        await self._shared_context.add_host_entry(
            danmaku=f"[礼物] {gift_info}",
            reply=spoken,
            user=user,
        )

        if self._on_reply:
            await self._on_reply(spoken)

    async def _llm_generate(self, system_content: str, user_content: str, max_tokens: int) -> str | None:
        ai = get_ai_client()
        if not ai.available:
            logger.warning("AI 不可用，跳过话术生成")
            return None

        messages = [
            ChatMessage(role="system", content=system_content),
            ChatMessage(role="user", content=user_content),
        ]

        request = ChatRequest(
            messages=messages,
            model=config.host_model,
            temperature=config.host_temperature,
            max_tokens=max_tokens,
        )

        try:
            response = await ai.chat(request)
            if not response or not response.content:
                logger.warning("主播 LLM 响应为空")
                return None

            text = response.content.strip()
            if len(text) > config.host_max_reply_length:
                text = text[:config.host_max_reply_length]
            return text

        except Exception as e:
            logger.error(f"主播 LLM 话术生成失败: {e}")
            return None

    async def _speak(self, text: str):
        elapsed = time.time() - self._last_tts_time
        min_interval = 3.0
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)

        tts = get_tts_client()
        try:
            result = await tts.synthesize(text)
            if result and result.audio_data:
                logger.debug(f"TTS 合成成功: {len(result.audio_data)} bytes")
        except Exception as e:
            logger.error(f"TTS 合成失败: {e}")

        self._last_tts_time = time.time()
