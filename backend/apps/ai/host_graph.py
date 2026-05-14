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
from collections.abc import Coroutine
from typing import Callable

from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
from apps.ai.host_brain import SentenceBuffer, StreamReplyChunk, get_host_brain
from apps.ai.messaging.queue import Message, get_message_queue
from apps.ai.prompt import get_host_system_prompt
from apps.ai.shared_context import get_shared_context
from apps.ai.tts import get_tts_client
from apps.config import config
from apps.easyvtuber import get_easyvtuber_manager

logger = logging.getLogger(__name__)

COMMENTARY_SYSTEM_PROMPT = """{host_personality}

【解说要点】
{key_points}

【建议情绪】
{mood}

【你刚才的互动】
{host_history}

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
        on_reply: Callable[[str], Coroutine] | None = None,
    ):
        self._shared_context = get_shared_context()
        self._running = False
        self._task: asyncio.Task | None = None
        self._on_reply = on_reply

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self):
        if self._running:
            logger.warning("主播 Graph 已在运行")
            return

        self._running = True
        brain = get_host_brain(config.default_room_id)
        await brain.start_polling()
        self._task = asyncio.create_task(self._host_loop())
        logger.info("主播 Graph 启动")

    async def stop(self):
        self._running = False
        brain = get_host_brain(config.default_room_id)
        await brain.stop_polling()
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
                queue.apply_priority_override()
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

        host_personality = get_host_system_prompt()
        host_history = await self._shared_context.get_host_history_text(limit=10)

        system_content = COMMENTARY_SYSTEM_PROMPT.format(
            host_personality=host_personality,
            key_points="\n".join(f"- {p}" for p in key_points),
            mood=mood,
            host_history=host_history or "（暂无）",
        )

        spoken = await self._stream_reply(system_content, "请生成解说。")
        if not spoken:
            return

        logger.info(f"主播解说: {spoken}")

        await self._shared_context.signal_commentary_consumed()

        await self._shared_context.add_host_entry(
            danmaku=f"[游戏解说-{mood}]",
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

        spoken = await self._stream_reply(system_content, "请回复弹幕。")
        if not spoken:
            return

        logger.info(f"主播回复弹幕 [{user}]: {spoken[:30]}...")

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

        spoken = await self._stream_reply(system_content, "请生成感谢语。")
        if not spoken:
            return

        logger.info(f"礼物感谢: {spoken}")

        await self._shared_context.add_host_entry(
            danmaku=f"[礼物] {gift_info}",
            reply=spoken,
            user=user,
        )

        if self._on_reply:
            await self._on_reply(spoken)

    async def _stream_reply(self, system_content: str, user_content: str) -> str | None:
        """流式 LLM → 分句 TTS → WebSocket 广播 → EasyVtuber 口型

        复用与 HostBrain._stream_reply_impl 完全相同的流式管线，
        唯一的区别是输出通过 WebSocket 广播而非 HTTP SSE yield。
        """
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
            top_p=config.host_top_p,
            max_tokens=config.host_max_tokens,
            disable_thinking=config.llm_disable_thinking,
            stream=True,
        )

        sentence_buffer = SentenceBuffer()
        full_response = ""
        sentence_index = 0
        char_offset = 0
        tts_tasks: list[asyncio.Task] = []

        tts = get_tts_client()

        async def process_sentence(sentence: str, idx: int, offset: int):
            result = await tts.synthesize(sentence)
            if result:
                return StreamReplyChunk(
                    type="audio",
                    text=sentence,
                    audio_data=result.audio_data,
                    sentence_index=idx,
                    char_offset=offset,
                )
            return None

        await self._broadcast_chunk({"type": "start", "is_final": False})

        try:
            easyvtuber = get_easyvtuber_manager()
            easyvtuber.set_speaking(True)
        except Exception as e:
            logger.warning(f"设置 speaking 状态失败: {e}")

        try:
            async for chunk in ai.chat_stream(request):
                full_response += chunk

                new_sentences = sentence_buffer.add(chunk)
                for sentence in new_sentences:
                    await self._broadcast_chunk({"type": "text", "text": sentence, "is_final": False})

                    task = asyncio.create_task(
                        process_sentence(sentence, sentence_index, char_offset)
                    )
                    tts_tasks.append(task)
                    sentence_index += 1
                    char_offset += len(sentence)

            remaining = sentence_buffer.flush()
            if remaining:
                await self._broadcast_chunk({"type": "text", "text": remaining, "is_final": False})

                task = asyncio.create_task(
                    process_sentence(remaining, sentence_index, char_offset)
                )
                tts_tasks.append(task)

            for task in tts_tasks:
                result = await task
                if result:
                    await self._broadcast_chunk(result.to_dict())

            if len(full_response) > config.host_max_reply_length:
                full_response = full_response[:config.host_max_reply_length]

            await self._broadcast_chunk({"type": "end", "text": full_response, "is_final": True})

        finally:
            try:
                easyvtuber = get_easyvtuber_manager()
                easyvtuber.set_speaking(False)
            except Exception as e:
                logger.warning(f"设置 speaking 状态失败: {e}")

        return full_response

    async def _broadcast_chunk(self, chunk: dict):
        """广播到所有前端 WebSocket"""
        from core.websocket import manager as ws_manager

        target_rooms = set()
        if config.bilibili_room_id > 0:
            target_rooms.add(str(config.bilibili_room_id))
        if config.default_room_id > 0:
            target_rooms.add(str(config.default_room_id))

        from apps.ai.admin_commands import get_admin_handler
        if get_admin_handler().get_state().is_test_room_enabled:
            target_rooms.add("test_room")

        for room_id in target_rooms:
            try:
                await ws_manager.send_message(room_id, chunk)
            except Exception:
                pass
