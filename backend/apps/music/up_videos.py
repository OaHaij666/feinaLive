"""UP主视频管理（MySQL）"""

import logging
from datetime import datetime

from bilibili_api import user, VideoOrder
from sqlalchemy import select, func, delete

from apps.db import UpVideo, get_session, init_db
from apps.config import config

logger = logging.getLogger(__name__)


class UpVideoManager:
    def __init__(self):
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        await init_db()
        await self._auto_refresh()
        self._initialized = True
        logger.info("UP视频管理器初始化完成")

    async def _auto_refresh(self):
        for up in config.trusted_ups:
            try:
                last = await self._get_last_fetch_time(up["uid"])
                now = datetime.now()
                if not last or (now - last).days >= config.full_refresh_days:
                    logger.info(f"UP主 {up['name']} 超过{config.full_refresh_days}天未更新，全量拉取")
                    await self._full_refresh(up)
                elif (now - last).days >= config.incremental_days:
                    logger.info(f"UP主 {up['name']} 超过{config.incremental_days}天未更新，增量拉取")
                    await self._incremental_refresh(up)
                else:
                    logger.debug(f"UP主 {up['name']} 无需更新")
            except Exception as e:
                logger.error(f"刷新UP主视频失败 {up['name']}: {e}")

    async def _get_last_fetch_time(self, up_uid: int) -> datetime | None:
        async with get_session() as session:
            result = await session.execute(
                select(func.max(UpVideo.fetched_at)).where(UpVideo.up_uid == up_uid)
            )
            return result.scalar_one_or_none()

    async def _full_refresh(self, up: dict):
        u = user.User(up["uid"])
        result = await u.get_videos(pn=1, ps=50, order=VideoOrder.PUBDATE)
        vlist = result.get("list", {}).get("vlist", [])
        async with get_session() as session:
            await session.execute(delete(UpVideo).where(UpVideo.up_uid == up["uid"]))
            for v in vlist:
                duration_str = v.get("length", "0")
                parts = duration_str.split(":") if ":" in duration_str else ["0"]
                duration = int(parts[0]) * 60 + int(parts[1]) if len(parts) >= 2 else 0
                video = UpVideo(
                    bvid=v.get("bvid", ""),
                    title=v.get("title", ""),
                    up_name=up["name"],
                    up_uid=up["uid"],
                    duration=duration,
                    cover_url=v.get("pic", ""),
                    fetched_at=datetime.now(),
                )
                session.add(video)
            await session.commit()
        logger.info(f"全量刷新 {up['name']}: 新增/更新 {len(vlist)} 个视频")

    async def _incremental_refresh(self, up: dict):
        u = user.User(up["uid"])
        result = await u.get_videos(pn=1, ps=20, order=VideoOrder.PUBDATE)
        vlist = result.get("list", {}).get("vlist", [])
        count = 0
        async with get_session() as session:
            for v in vlist:
                bvid = v.get("bvid", "")
                existing = await session.execute(
                    select(UpVideo).where(UpVideo.bvid == bvid)
                )
                if existing.scalar_one_or_none() is None:
                    duration_str = v.get("length", "0")
                    parts = duration_str.split(":") if ":" in duration_str else ["0"]
                    duration = int(parts[0]) * 60 + int(parts[1]) if len(parts) >= 2 else 0
                    video = UpVideo(
                        bvid=bvid,
                        title=v.get("title", ""),
                        up_name=up["name"],
                        up_uid=up["uid"],
                        duration=duration,
                        cover_url=v.get("pic", ""),
                        fetched_at=datetime.now(),
                    )
                    session.add(video)
                    count += 1
            await session.commit()
        logger.info(f"增量刷新 {up['name']}: 新增 {count} 个视频")

    async def search(self, keyword: str, limit: int = 10) -> list[dict]:
        kw = keyword.strip().lower()
        async with get_session() as session:
            result = await session.execute(
                select(UpVideo)
                .where(UpVideo.title.ilike(f"%{kw}%"))
                .order_by(UpVideo.fetched_at.desc())
                .limit(limit)
            )
            videos = result.scalars().all()
            return [
                {
                    "bvid": v.bvid,
                    "title": v.title,
                    "upName": v.up_name,
                    "duration": v.duration,
                    "coverUrl": v.cover_url,
                }
                for v in videos
            ]

    async def ensure_fetched(self):
        if not self._initialized:
            await self.initialize()


_up_video_manager: UpVideoManager | None = None


def get_up_video_manager() -> UpVideoManager:
    global _up_video_manager
    if _up_video_manager is None:
        _up_video_manager = UpVideoManager()
    return _up_video_manager
