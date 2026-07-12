"""Message-specific planning and persistence for the host runtime."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from apps.agent.mutual_context import MutualContext, get_mutual_context
from apps.ai.memory.engine import get_memory_engine
from apps.ai.messaging.queue import Message
from apps.ai.prompt import get_host_system_prompt
from apps.ai.shared_context import SharedContext, get_shared_context
from apps.ai.speech_jobs import (
    SpeechJobCoordinator,
    SpeechJobStatus,
    get_speech_job_coordinator,
)
from apps.ai.speech_pipeline import SpeechPipeline
from apps.live.room_session import RoomSessionContext, get_room_session_manager

logger = logging.getLogger(__name__)

ReplyCallback = Callable[[str], Awaitable[None]]

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

    def __init__(
        self,
        shared_context: SharedContext | None = None,
        mutual_context: MutualContext | None = None,
    ) -> None:
        self._shared_context = shared_context or get_shared_context()
        self._mutual_context = mutual_context or get_mutual_context()

    async def _recent_context(self, legacy_limit: int) -> str:
        legacy = await self._shared_context.get_host_history_text(limit=legacy_limit)
        mutual = await self._mutual_context.to_prompt_text(limit=10)
        return f"{legacy}\n{mutual}" if legacy else mutual

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

        host_history = await self._recent_context(10)
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
        host_history = await self._recent_context(5)
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
        mutual_context: MutualContext | None = None,
        speech_jobs: SpeechJobCoordinator | None = None,
    ) -> None:
        self._shared_context = shared_context or get_shared_context()
        self._mutual_context = mutual_context or get_mutual_context()
        self._planner = planner or HostPromptPlanner(self._shared_context, self._mutual_context)
        self._speech = speech or SpeechPipeline()
        self._on_reply = on_reply
        self._speech_jobs = speech_jobs or get_speech_job_coordinator()

    async def handle_prepared_speech(self, message: Message) -> None:
        """Play Agent-authored final text without invoking another LLM."""

        job_id = str(message.data.get("speech_job_id", ""))
        jobs = self._speech_jobs

        async def on_started(reply_id: str) -> None:
            await jobs.started(job_id, reply_id)

        try:
            result = await self._speech.speak_text(
                message.content,
                self.context_for(message),
                on_playback_started=on_started,
            )
        except asyncio.CancelledError:
            await jobs.finish(
                job_id,
                SpeechJobStatus.CANCELLED,
                error="HostRuntime stopped during prepared speech",
            )
            raise
        except Exception as exc:
            await jobs.finish(job_id, SpeechJobStatus.FAILED, error=str(exc))
            raise

        if result and result.played:
            await jobs.finish(
                job_id,
                SpeechJobStatus.FINISHED,
                reply_id=result.reply_id,
            )
            await self._mutual_context.record(
                "host",
                "spoken",
                result.text,
                {"reply_id": result.reply_id, "source": "agent_commentary"},
            )
            await self._notify(result.text)
            return

        await jobs.finish(
            job_id,
            SpeechJobStatus.FAILED,
            reply_id=result.reply_id if result else "",
            error=(result.playback_error or result.playback_status) if result else "invalid room",
        )

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
        await self._mutual_context.record(
            "host",
            "spoken",
            spoken,
            {"source": "danmaku", "viewer_message": message.content[:300], "user": user},
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
        await self._mutual_context.record(
            "host",
            "spoken",
            spoken,
            {"source": "gift", "user": user},
        )
        await self._notify(spoken)

    async def fail(self, message: Message, error: Exception) -> None:
        if message.msg_type == "prepared_speech":
            await self._speech_jobs.finish(
                str(message.data.get("speech_job_id", "")),
                SpeechJobStatus.FAILED,
                error=str(error),
            )
        logger.debug("Host message failed: type=%s error=%s", message.msg_type, error)

    @staticmethod
    def context_for(message: Message) -> RoomSessionContext | None:
        """Never replace malformed routing context with the current room."""

        if message.context:
            return RoomSessionContext.from_mapping(message.context)
        return get_room_session_manager().active_context

    async def _notify(self, spoken: str) -> None:
        if self._on_reply:
            await self._on_reply(spoken)
