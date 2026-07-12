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
from apps.ai.memory.engine import get_memory_engine
from apps.ai.messaging.queue import Message, get_message_queue
from apps.ai.prompt import get_host_system_prompt
from apps.ai.shared_context import get_shared_context
from apps.ai.tts import get_tts_client
from apps.config import config
from apps.easyvtuber import get_easyvtuber_manager
from apps.live.room_session import RoomSessionContext, get_room_session_manager

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

{viewer_memory}

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

    MAX_RETRY_COUNT = 2
    RETRY_DELAY_SECONDS = 1.0

    async def _host_loop(self):
        queue = get_message_queue()
        retry_count = 0

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

                retry_count = 0

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                retry_count += 1
                if retry_count <= self.MAX_RETRY_COUNT:
                    logger.warning(f"主播循环异常 (重试 {retry_count}/{self.MAX_RETRY_COUNT}): {e}")
                    await asyncio.sleep(self.RETRY_DELAY_SECONDS * retry_count)
                else:
                    logger.error(f"主播循环连续失败 {retry_count} 次，跳过当前消息: {e}", exc_info=True)
                    retry_count = 0

    async def _handle_commentary(self, msg: Message):
        data = msg.data
        request_id = data.get("commentary_request_id", "")
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

        try:
            spoken = await self._stream_reply(
                system_content,
                "请生成解说。",
                self._context_for_message(msg),
            )
        except Exception as e:
            logger.error(f"解说生成失败: {e}", exc_info=True)
            spoken = None
            if request_id:
                await self._shared_context.signal_commentary_status(
                    request_id,
                    "llm_failed",
                    error=str(e),
                )
            return

        if not spoken:
            if request_id:
                await self._shared_context.signal_commentary_status(
                    request_id,
                    "llm_failed",
                    error="主播解说生成为空",
                )
            return

        logger.info(f"主播解说: {spoken}")

        await self._shared_context.add_host_entry(
            danmaku=f"[游戏解说-{mood}]",
            reply=spoken,
        )
        if request_id:
            await self._shared_context.signal_commentary_status(
                request_id,
                "spoken",
                spoken_text=spoken,
            )
        else:
            await self._shared_context.signal_commentary_consumed()

        if self._on_reply:
            await self._on_reply(spoken)

    async def _handle_danmaku(self, msg: Message):
        danmaku = msg.content
        user = msg.data.get("user", "unknown")
        uid = msg.data.get("uid")
        memory_user_id = str(uid) if uid else user

        host_personality = get_host_system_prompt()
        host_history = await self._shared_context.get_host_history_text(limit=10)

        # 注入观众记忆
        viewer_memory = ""
        try:
            engine = get_memory_engine()
            viewer_memory = await engine.inject_for_host(user_id=memory_user_id)
            if viewer_memory:
                viewer_memory = f"【关于这位观众】\n{viewer_memory}"
        except Exception as e:
            logger.debug(f"观众记忆注入失败: {e}")

        system_content = DANMAKU_REPLY_PROMPT.format(
            host_personality=host_personality,
            viewer_memory=viewer_memory or "（暂无观众记忆）",
            danmaku=danmaku,
            host_history=host_history or "（暂无）",
        )

        spoken = await self._stream_reply(
            system_content,
            "请回复弹幕。",
            self._context_for_message(msg),
        )
        if not spoken:
            return

        logger.info(f"主播回复弹幕 [{user}]: {spoken[:30]}...")

        await self._shared_context.add_host_entry(
            danmaku=danmaku,
            reply=spoken,
            user=user,
        )

        # 只记忆主播真正回复过的弹幕互动；未回复弹幕不进入长期用户记忆。
        try:
            engine = get_memory_engine()
            asyncio.create_task(engine.extract_and_store(
                source="interaction",
                content=danmaku,
                context={"user_id": memory_user_id, "username": user, "danmaku": danmaku, "reply": spoken},
            ))
            from apps.ai.memory import get_user_profile, trigger_summary_if_needed
            profile = get_user_profile(memory_user_id, user)
            profile.add_conversation(danmaku, spoken)
            trigger_summary_if_needed(profile)
        except Exception as e:
            logger.debug(f"回复互动记忆调度失败: {e}")

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

        spoken = await self._stream_reply(
            system_content,
            "请生成感谢语。",
            self._context_for_message(msg),
        )
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

    async def _stream_reply(
        self,
        system_content: str,
        user_content: str,
        context: RoomSessionContext | None,
    ) -> str | None:
        """流式 LLM → 分句 TTS → WebSocket 广播 → EasyVtuber 口型

        复用与 HostBrain._stream_reply_impl 完全相同的流式管线，
        唯一的区别是输出通过 WebSocket 广播而非 HTTP SSE yield。
        """
        if context is None or not get_room_session_manager().is_current(context):
            logger.debug("Skipped reply generation without a current room session")
            return None

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

        await self._broadcast_chunk({"type": "start", "is_final": False}, context)

        try:
            easyvtuber = get_easyvtuber_manager()
            easyvtuber.set_speaking(True)
        except Exception as e:
            logger.warning(f"设置 speaking 状态失败: {e}")

        try:
            async for chunk in ai.chat_stream(request):
                if not get_room_session_manager().is_current(context):
                    for task in tts_tasks:
                        task.cancel()
                    logger.info("Cancelled reply because the active room session changed")
                    return None
                full_response += chunk

                new_sentences = sentence_buffer.add(chunk)
                for sentence in new_sentences:
                    await self._broadcast_chunk(
                        {"type": "text", "text": sentence, "is_final": False},
                        context,
                    )

                    task = asyncio.create_task(
                        process_sentence(sentence, sentence_index, char_offset)
                    )
                    tts_tasks.append(task)
                    sentence_index += 1
                    char_offset += len(sentence)

            remaining = sentence_buffer.flush()
            if remaining:
                await self._broadcast_chunk(
                    {"type": "text", "text": remaining, "is_final": False},
                    context,
                )

                task = asyncio.create_task(
                    process_sentence(remaining, sentence_index, char_offset)
                )
                tts_tasks.append(task)

            for task in tts_tasks:
                if not get_room_session_manager().is_current(context):
                    for pending in tts_tasks:
                        pending.cancel()
                    return None
                result = await task
                if result:
                    await self._broadcast_chunk(result.to_dict(), context)

            if len(full_response) > config.host_max_reply_length:
                full_response = full_response[:config.host_max_reply_length]

            if not get_room_session_manager().is_current(context):
                return None

            await self._broadcast_chunk(
                {"type": "end", "text": full_response, "is_final": True},
                context,
            )

        finally:
            try:
                easyvtuber = get_easyvtuber_manager()
                easyvtuber.set_speaking(False)
            except Exception as e:
                logger.warning(f"设置 speaking 状态失败: {e}")

        return full_response

    def _context_for_message(self, msg: Message) -> RoomSessionContext | None:
        context = RoomSessionContext.from_mapping(msg.context)
        if context is not None:
            return context
        return get_room_session_manager().active_context

    async def _broadcast_chunk(
        self,
        chunk: dict,
        context: RoomSessionContext | None,
    ) -> None:
        """Route output only to the session that produced the consumed message."""

        if context is None or not get_room_session_manager().is_current(context):
            logger.debug("Dropped reply chunk without a current room session")
            return

        from core.websocket import manager as ws_manager

        chunk.setdefault("context", context.to_dict())
        await ws_manager.send_message(context.room_id, chunk)
