"""预备歌单管理"""

import logging
import random

from sqlalchemy import select

from apps.db import PlaylistItem, get_db_session, init_db
from apps.music.client import BilibiliMusicClient
from apps.music.models import MusicLibraryItem, MusicLibraryResponse
from apps.config import config

logger = logging.getLogger(__name__)


class PlaylistManager:
    def __init__(self):
        self._initialized = False
        self._client = BilibiliMusicClient()

    async def initialize(self):
        if self._initialized:
            return
        await init_db()
        async with get_db_session() as session:
            result = await session.execute(select(PlaylistItem))
            existing = result.scalars().all()
            if not existing:
                default_items = config.default_playlist
                for item_data in default_items:
                    item = PlaylistItem(**item_data)
                    session.add(item)
                await session.commit()
                logger.info(f"预备歌单初始化完成，共 {len(default_items)} 首")
        self._initialized = True

    async def get_all(self) -> MusicLibraryResponse:
        await self.initialize()
        async with get_db_session() as session:
            result = await session.execute(
                select(PlaylistItem).where(PlaylistItem.enabled == True)
            )
            items = result.scalars().all()
            return MusicLibraryResponse(
                items=[
                    MusicLibraryItem(
                        id=str(item.id),
                        bvid=item.bvid,
                        title=item.title,
                        upName=item.artist,
                        duration=0,
                        coverUrl="",
                        enabled=item.enabled,
                    )
                    for item in items
                ],
                total=len(items),
            )

    async def add(self, bvid: str, title: str = "", artist: str = "", enabled: bool = True) -> MusicLibraryItem | None:
        await self.initialize()
        async with get_db_session() as session:
            existing = await session.execute(select(PlaylistItem).where(PlaylistItem.bvid == bvid))
            if existing.scalar_one_or_none():
                logger.warning(f"预备歌单中已存在: {bvid}")
                result = await session.execute(select(PlaylistItem).where(PlaylistItem.bvid == bvid))
                item = result.scalar_one()
                return MusicLibraryItem(
                    id=str(item.id), bvid=item.bvid, title=item.title,
                    upName=item.artist, duration=0, coverUrl="",
                    enabled=item.enabled,
                )
            item = PlaylistItem(bvid=bvid, title=title or bvid, artist=artist, enabled=enabled)
            session.add(item)
            await session.commit()
            await session.refresh(item)
            logger.info(f"预备歌单添加: {bvid} - {title}")
            return MusicLibraryItem(
                id=str(item.id), bvid=item.bvid, title=item.title,
                upName=item.artist, duration=0, coverUrl="",
                enabled=item.enabled,
            )

    async def add_from_bv(self, bvid: str) -> MusicLibraryItem | None:
        try:
            info = await self._client.get_video_info(bvid)
            if not info:
                logger.error(f"获取视频信息失败: {bvid}")
                return None
            owner = info.get("owner", {})
            return await self.add(
                bvid=bvid,
                title=info.get("title", ""),
                artist=owner.get("name", "未知UP主"),
            )
        except Exception as e:
            logger.error(f"从BV号添加音乐失败: {bvid}, error: {e}")
            return None

    async def remove(self, bvid: str) -> bool:
        await self.initialize()
        async with get_db_session() as session:
            result = await session.execute(select(PlaylistItem).where(PlaylistItem.bvid == bvid))
            item = result.scalar_one_or_none()
            if not item:
                return False
            await session.delete(item)
            await session.commit()
            logger.info(f"预备歌单移除: {bvid}")
            return True

    async def set_enabled(self, bvid: str, enabled: bool) -> bool:
        await self.initialize()
        async with get_db_session() as session:
            result = await session.execute(select(PlaylistItem).where(PlaylistItem.bvid == bvid))
            item = result.scalar_one_or_none()
            if not item:
                return False
            item.enabled = enabled
            await session.commit()
            logger.info(f"预备歌单设置启用状态: {bvid} = {enabled}")
            return True

    async def random_pick(self) -> MusicLibraryItem | None:
        await self.initialize()
        async with get_db_session() as session:
            result = await session.execute(
                select(PlaylistItem).where(PlaylistItem.enabled == True)
            )
            items = result.scalars().all()
            if not items:
                logger.warning("预备歌单为空，无法随机抽取")
                return None
            picked = random.choice(items)
            return MusicLibraryItem(
                id=str(picked.id), bvid=picked.bvid, title=picked.title,
                upName=picked.artist, duration=0, coverUrl="",
                enabled=picked.enabled,
            )


_playlist_manager: PlaylistManager | None = None


def get_playlist_manager() -> PlaylistManager:
    global _playlist_manager
    if _playlist_manager is None:
        _playlist_manager = PlaylistManager()
    return _playlist_manager
