"""播放队列管理"""

import asyncio
import logging
from collections import deque
from datetime import datetime
from typing import Optional, Callable, Awaitable

from apps.music.models import MusicItem, MusicStatus, QueueStats

logger = logging.getLogger(__name__)


class MusicQueue:
    def __init__(self, max_history: int = 100):
        self._queue: deque[MusicItem] = deque(maxlen=200)
        self._current: Optional[MusicItem] = None
        self._history: deque[MusicItem] = deque(maxlen=max_history)
        self._lock = asyncio.Lock()
        self._play_callback: Optional[Callable[[MusicItem], Awaitable[None]]] = None
        self._play_task: Optional[asyncio.Task] = None
        self._total_played = 0
        self._volume: float = 1.0

    def set_play_callback(self, callback: Callable[[MusicItem], Awaitable[None]]):
        self._play_callback = callback

    def set_volume(self, volume: float):
        self._volume = max(0.0, min(1.0, volume))
        logger.info(f"音量已设置为 {self._volume}")

    def get_volume(self) -> float:
        return self._volume

    async def add(self, item: MusicItem) -> bool:
        async with self._lock:
            self._queue.append(item)
            logger.info(f"音乐加入队列: {item.title} by {item.requestedBy}")
            return True

    async def add_multiple(self, items: list[MusicItem]) -> int:
        count = 0
        async with self._lock:
            for item in items:
                if len(self._queue) < 200:
                    self._queue.append(item)
                    count += 1
        if count > 0:
            logger.info(f"批量加入 {count} 首音乐到队列")
        return count

    async def next(self) -> Optional[MusicItem]:
        async with self._lock:
            if self._current:
                self._current.status = MusicStatus.COMPLETED
                self._current.playedAt = datetime.now()
                self._history.append(self._current)
                self._total_played += 1
            if self._queue:
                self._current = self._queue.popleft()
                self._current.status = MusicStatus.PLAYING
                self._current.playedAt = datetime.now()
                return self._current
            else:
                self._current = None
                return None

    async def skip(self) -> Optional[MusicItem]:
        return await self.next()

    async def remove(self, item_id: str) -> bool:
        async with self._lock:
            for i, item in enumerate(self._queue):
                if item.id == item_id:
                    del self._queue[i]
                    logger.info(f"从队列移除: {item.title}")
                    return True
            return False

    async def clear(self) -> int:
        async with self._lock:
            count = len(self._queue)
            self._queue.clear()
            logger.info(f"清空队列, 移除 {count} 首")
            return count

    async def get_current(self) -> Optional[MusicItem]:
        async with self._lock:
            return self._current

    async def get_current_bvid(self) -> Optional[str]:
        async with self._lock:
            return self._current.bvid if self._current else None

    async def skip_and_disable_current(self) -> Optional[str]:
        async with self._lock:
            bvid = self._current.bvid if self._current else None
            if self._current:
                self._current.status = MusicStatus.COMPLETED
                self._current.playedAt = datetime.now()
                self._history.append(self._current)
                self._total_played += 1
            if self._queue:
                self._current = self._queue.popleft()
                self._current.status = MusicStatus.PLAYING
                self._current.playedAt = datetime.now()
            else:
                self._current = None
            return bvid

    async def get_queue(self) -> list[MusicItem]:
        async with self._lock:
            return list(self._queue)

    async def get_history(self) -> list[MusicItem]:
        async with self._lock:
            return list(self._history)

    async def get_stats(self) -> QueueStats:
        async with self._lock:
            return QueueStats(
                total_played=self._total_played,
                total_queue=len(self._queue),
                current=self._current,
            )

    async def start_auto_play(self):
        if self._play_task is None or self._play_task.done():
            self._play_task = asyncio.create_task(self._auto_play_loop())
            logger.info("自动播放循环已启动")

    async def stop_auto_play(self):
        if self._play_task and not self._play_task.done():
            self._play_task.cancel()
            try:
                await self._play_task
            except asyncio.CancelledError:
                pass
            logger.info("自动播放循环已停止")

    async def _auto_play_loop(self):
        while True:
            try:
                current = await self.get_current()
                if current is None:
                    current = await self.next()
                if current is None:
                    await asyncio.sleep(2)
                    continue
                if self._play_callback:
                    try:
                        await self._play_callback(current)
                    except Exception as e:
                        logger.error(f"播放回调执行失败: {e}")
                if current.duration > 0:
                    await asyncio.sleep(current.duration + 2)
                else:
                    await asyncio.sleep(180)
                await self.next()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动播放循环异常: {e}")
                await asyncio.sleep(5)


_music_queue: Optional[MusicQueue] = None


def get_music_queue() -> MusicQueue:
    global _music_queue
    if _music_queue is None:
        _music_queue = MusicQueue()
    return _music_queue
