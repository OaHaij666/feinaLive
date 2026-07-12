"""Commentary request coordination between GameGraph and HostRuntime."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from apps.ai.messaging.queue import PRIORITY_HIGH, Message, get_message_queue
from apps.ai.shared_context import CommentaryAck, SharedContext
from apps.config import config
from apps.live.room_session import get_room_session_manager

logger = logging.getLogger(__name__)


@dataclass
class CommentaryRequest:
    key_points: list[str] = field(default_factory=list)
    mood: str = "neutral"
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommentaryEnqueueResult:
    request_id: str
    cancel_key: str
    enqueued: bool
    ack: CommentaryAck | None = None


class CommentaryCoordinator:
    """Merge, throttle, enqueue, and await commentary requests."""

    def __init__(
        self,
        shared_context: SharedContext,
        game_id: str,
        min_interval: float | None = None,
    ):
        self._shared_context = shared_context
        self._game_id = game_id
        self._min_interval = (
            min_interval if min_interval is not None else config.game_min_commentary_interval
        )

    def merge_requests(self, requests: list[dict]) -> CommentaryRequest | None:
        key_points: list[str] = []
        seen: set[str] = set()
        mood = "neutral"
        merged_data: dict[str, Any] = {}

        for req in requests:
            if not isinstance(req, dict):
                continue
            if mood == "neutral" and req.get("mood"):
                mood = req.get("mood", "neutral")
            elif req.get("mood") and req.get("mood") != "neutral":
                mood = req.get("mood")

            for point in req.get("key_points", []) or []:
                text = str(point).strip()
                if text and text not in seen:
                    seen.add(text)
                    key_points.append(text)
            merged_data.update(req)

        if not key_points:
            return None
        return CommentaryRequest(key_points=key_points, mood=mood or "neutral", data=merged_data)

    async def enqueue_and_wait(
        self,
        requests: list[dict],
        timeout: float | None = None,
    ) -> CommentaryAck | None:
        merged = self.merge_requests(requests)
        if not merged:
            return None

        now = time.time()
        last_consumed = await self._shared_context.get_last_commentary_time()
        if now - last_consumed < self._min_interval:
            logger.debug(
                "距上次成功解说仅 %.1fs，小于硬间隔 %.1fs，跳过",
                now - last_consumed,
                self._min_interval,
            )
            return None

        game_step_id = await self._shared_context.get_game_step_id()
        request_id = str(uuid.uuid4())
        cancel_key = f"commentary_{self._game_id}_{request_id}"
        await self._shared_context.register_commentary_request(request_id, game_step_id)

        queue = get_message_queue()
        requested_timeout = timeout if timeout is not None else config.game_commentary_hold_timeout
        # `spoken` now means browser playback really finished, not merely that
        # audio bytes were generated. Keep the game-side waiter alive across
        # generation, TTS, and the playback acknowledgement window.
        hold_timeout = max(requested_timeout, config.host_playback_timeout_seconds + 30.0)
        msg = Message(
            priority=PRIORITY_HIGH,
            source="game",
            msg_type="commentary_request",
            content=" | ".join(merged.key_points),
            data={
                "commentary_request_id": request_id,
                "key_points": merged.key_points,
                "mood": merged.mood,
                "game_step_id": game_step_id,
            },
            context=(
                get_room_session_manager().active_context.to_dict()
                if get_room_session_manager().active_context
                else {}
            ),
            cancel_key=cancel_key,
            expire_at=now + hold_timeout + 5,
            allow_skip=False,
        )

        success = await queue.put(msg)
        if not success:
            ack = await self._shared_context.signal_commentary_status(
                request_id,
                "dropped",
                error="解说消息入队失败",
            )
            await self._shared_context.release_commentary_request(request_id)
            return ack

        logger.info(
            "解说请求入队: %s (step=%s, id=%s)", merged.key_points, game_step_id, request_id
        )
        await self._shared_context.add_game_entry(
            action="request_host_commentary",
            params={"key_points": merged.key_points, "mood": merged.mood, "request_id": request_id},
            result="enqueued",
            game_id=self._game_id,
        )

        try:
            ack = await self._shared_context.wait_commentary_status(request_id, hold_timeout)
            if ack.status == "timeout":
                queue.cancel(cancel_key)
                logger.info("解说等待超时，已取消未消费消息: id=%s", request_id)
            return ack
        finally:
            await self._shared_context.release_commentary_request(request_id)
