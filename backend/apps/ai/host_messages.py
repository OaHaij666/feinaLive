"""Message-specific planning and persistence for the host runtime."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from apps.ai.memory.engine import get_memory_engine
from apps.ai.messaging.queue import Message
from apps.ai.prompt import get_host_system_prompt
from apps.ai.shared_context import SharedContext, get_shared_context
from apps.ai.speech_pipeline import SpeechPipeline
from apps.live.room_session import RoomSessionContext, get_room_session_manager

logger = logging.getLogger(__name__)

ReplyCallback = Callable[[str], Awaitable[None]]

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
- 长度控制在20-50字
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
- 长度控制在20-50字"""

GIFT_THANKS_PROMPT = """{host_personality}

【你刚才的互动】
{host_history}

观众送了礼物: {gift_info}

请生成一段感谢语:
- 用第一人称
- 口语化、自然
- 长度控制在15-30字
- 感谢要真诚不油腻"""


@dataclass
class DanmakuReplyPlan:
    system_content: str
    profile: Any | None
    memory_user_id: str


class HostPromptPlanner:
    """Build host prompts without owning queue or output lifecycle."""

    def __init__(self, shared_context: SharedContext | None = None) -> None:
        self._shared_context = shared_context or get_shared_context()

    async def commentary(self, message: Message) -> str:
        data = message.data
        host_history = await self._shared_context.get_host_history_text(limit=10)
        return COMMENTARY_SYSTEM_PROMPT.format(
            host_personality=get_host_system_prompt(),
            key_points="\n".join(f"- {point}" for point in data.get("key_points", [])),
            mood=data.get("mood", "neutral"),
            host_history=host_history or "（暂无）",
        )

    async def danmaku(self, message: Message) -> DanmakuReplyPlan:
        user = message.data.get("user", "unknown")
        uid = message.data.get("uid")
        memory_user_id = str(uid) if uid else user
        memory_sections: list[str] = []
        profile = None

        try:
            from apps.ai.memory.user_profile import get_user_profile

            profile = get_user_profile(memory_user_id, user)
            profile_context = profile.get_memory_context()
            if profile_context:
                memory_sections.append("【用户概况与近期上下文】\n" + profile_context)
        except Exception as exc:
            logger.debug("用户画像加载失败: %s", exc)

        try:
            recalled = await get_memory_engine().inject_for_host(
                user_id=memory_user_id,
                query=message.content,
            )
            if recalled:
                memory_sections.append(recalled)
        except Exception as exc:
            logger.debug("观众记忆注入失败: %s", exc)

        host_history = await self._shared_context.get_host_history_text(limit=10)
        system_content = DANMAKU_REPLY_PROMPT.format(
            host_personality=get_host_system_prompt(),
            viewer_memory="\n\n".join(memory_sections) or "（暂无观众记忆）",
            danmaku=message.content,
            host_history=host_history or "（暂无）",
        )
        return DanmakuReplyPlan(
            system_content=system_content,
            profile=profile,
            memory_user_id=memory_user_id,
        )

    async def gift(self, message: Message) -> str:
        host_history = await self._shared_context.get_host_history_text(limit=5)
        return GIFT_THANKS_PROMPT.format(
            host_personality=get_host_system_prompt(),
            host_history=host_history or "（暂无）",
            gift_info=message.data.get("gift_info", message.content),
        )


class HostMessageProcessor:
    """Handle validated queue messages through planning, speech, and commit."""

    def __init__(
        self,
        shared_context: SharedContext | None = None,
        planner: HostPromptPlanner | None = None,
        speech: SpeechPipeline | None = None,
        on_reply: ReplyCallback | None = None,
    ) -> None:
        self._shared_context = shared_context or get_shared_context()
        self._planner = planner or HostPromptPlanner(self._shared_context)
        self._speech = speech or SpeechPipeline()
        self._on_reply = on_reply

    async def handle_commentary(self, message: Message) -> None:
        request_id = str(message.data.get("commentary_request_id", ""))
        mood = message.data.get("mood", "neutral")
        try:
            result = await self._speech.stream_reply(
                await self._planner.commentary(message),
                "请生成解说。",
                self.context_for(message),
            )
        except Exception as exc:
            logger.error("解说生成失败: %s", exc, exc_info=True)
            if request_id:
                await self._shared_context.signal_commentary_status(
                    request_id,
                    "llm_failed",
                    error=str(exc),
                )
            return

        if not result:
            if request_id:
                await self._shared_context.signal_commentary_status(
                    request_id,
                    "llm_failed",
                    error="主播解说生成为空或房间会话已失效",
                )
            return

        if not result.played:
            logger.warning(
                "解说未完成真实播放: reply=%s status=%s error=%s",
                result.reply_id,
                result.playback_status,
                result.playback_error,
            )
            if request_id:
                await self._shared_context.signal_commentary_status(
                    request_id,
                    "failed",
                    error=result.playback_error or result.playback_status,
                )
            return

        spoken = result.text

        logger.info("主播解说: %s", spoken)
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
        await self._notify(spoken)

    async def handle_danmaku(self, message: Message) -> None:
        user = message.data.get("user", "unknown")
        plan = await self._planner.danmaku(message)
        result = await self._speech.stream_reply(
            plan.system_content,
            "请回复弹幕。",
            self.context_for(message),
        )
        if not result or not result.played:
            if result:
                logger.warning(
                    "弹幕回复未完成真实播放: reply=%s status=%s error=%s",
                    result.reply_id,
                    result.playback_status,
                    result.playback_error,
                )
            return

        spoken = result.text

        logger.info("主播回复弹幕 [%s]: %s...", user, spoken[:30])
        await self._shared_context.add_host_entry(
            danmaku=message.content,
            reply=spoken,
            user=user,
        )

        try:
            from apps.ai.memory import trigger_summary_if_needed
            from apps.ai.memory.user_profile import get_user_profile

            profile = plan.profile or get_user_profile(plan.memory_user_id, user)
            profile.add_conversation(message.content, spoken)
            trigger_summary_if_needed(profile)
        except Exception as exc:
            logger.debug("回复互动记忆调度失败: %s", exc)
        await self._notify(spoken)

    async def handle_gift(self, message: Message) -> None:
        gift_info = message.data.get("gift_info", message.content)
        user = message.data.get("user", "")
        result = await self._speech.stream_reply(
            await self._planner.gift(message),
            "请生成感谢语。",
            self.context_for(message),
        )
        if not result or not result.played:
            if result:
                logger.warning(
                    "礼物感谢未完成真实播放: reply=%s status=%s error=%s",
                    result.reply_id,
                    result.playback_status,
                    result.playback_error,
                )
            return

        spoken = result.text

        logger.info("礼物感谢: %s", spoken)
        await self._shared_context.add_host_entry(
            danmaku=f"[礼物] {gift_info}",
            reply=spoken,
            user=user,
        )
        await self._notify(spoken)

    async def fail(self, message: Message, error: Exception) -> None:
        if message.msg_type != "commentary_request":
            return
        request_id = str(message.data.get("commentary_request_id", ""))
        if request_id:
            await self._shared_context.signal_commentary_status(
                request_id,
                "failed",
                error=str(error),
            )

    @staticmethod
    def context_for(message: Message) -> RoomSessionContext | None:
        """Never replace malformed routing context with the current room."""

        if message.context:
            return RoomSessionContext.from_mapping(message.context)
        return get_room_session_manager().active_context

    async def _notify(self, spoken: str) -> None:
        if self._on_reply:
            await self._on_reply(spoken)
