"""UP主视频管理"""

import asyncio
import hashlib
import logging
import time
import urllib.parse
from datetime import datetime
from functools import reduce

import httpx
from sqlalchemy import delete, func, select

from apps.config import config
from apps.db import UpVideo, get_db_session, init_db

logger = logging.getLogger(__name__)


OE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Referer": "https://www.bilibili.com",
}


def _decode_sessdata(sessdata: str) -> str:
    if "%" in sessdata:
        return urllib.parse.unquote(sessdata)
    return sessdata


def _get_mixin_key(img_url: str, sub_url: str) -> str:
    img_key = img_url.split("/")[-1].split(".")[0]
    sub_key = sub_url.split("/")[-1].split(".")[0]
    ae = img_key + sub_key
    le = reduce(lambda s, i: s + (ae[i] if i < len(ae) else ""), OE, "")
    return le[:32]


def _enc_wbi(params: dict, mixin_key: str) -> dict:
    params = dict(params)
    params.pop("w_rid", None)
    params["wts"] = int(time.time())
    if not params.get("web_location"):
        params["web_location"] = 1550101
    ae = urllib.parse.urlencode(sorted(params.items()))
    params["w_rid"] = hashlib.md5((ae + mixin_key).encode(encoding="utf-8")).hexdigest()
    return params


async def _fetch_videos_page(mid: int, pn: int, ps: int = 50) -> tuple[list[dict], bool, int]:
    raw_sessdata = config.bilibili_sessdata
    if not raw_sessdata:
        logger.warning("未配置 bilibili sessdata，无法获取UP主视频")
        return [], False, 0

    sessdata = _decode_sessdata(raw_sessdata)

    async with httpx.AsyncClient() as client:
        nav_resp = await client.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers={**_HEADERS, "Cookie": f"SESSDATA={sessdata}"},
        )
        nav_data = nav_resp.json()
        img_url = nav_data["data"]["wbi_img"]["img_url"]
        sub_url = nav_data["data"]["wbi_img"]["sub_url"]
        mixin_key = _get_mixin_key(img_url, sub_url)

        params = {"mid": mid, "ps": ps, "pn": pn, "order": "pubdate"}
        params = _enc_wbi(params, mixin_key)

        query = urllib.parse.urlencode(sorted(params.items()))
        search_resp = await client.get(
            f"https://api.bilibili.com/x/space/wbi/arc/search?{query}",
            headers={**_HEADERS, "Cookie": f"SESSDATA={sessdata}"},
        )

        if search_resp.status_code == 412:
            return [], True, 0

        data = search_resp.json()
        if data.get("code") != 0:
            msg = data.get("message", "")
            if "风控" in msg or "403" in msg or "触发" in msg:
                logger.warning(f"触发风控限制: {msg}")
                return [], True, 0
            logger.error(f"B站API错误: {msg}")
            return [], False, 0

        vlist = data.get("data", {}).get("list", {}).get("vlist", [])
        total_count = data.get("data", {}).get("page", {}).get("count", 0)
        return vlist, False, total_count


async def _fetch_videos(mid: int, ps: int = 50) -> list[dict]:
    all_videos = []
    pn = 1
    total_count = 0
    while True:
        vlist, rate_limited, total = await _fetch_videos_page(mid, pn, ps)

        if rate_limited:
            logger.warning("触发限流，停止拉取")
            break

        if not vlist:
            break

        all_videos.extend(vlist)
        total_count = total

        total_pn = (total_count + ps - 1) // ps if total_count > 0 else 1
        if pn >= total_pn:
            break
        pn += 1
        await asyncio.sleep(1.5)

    return all_videos


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
                logger.info(f"开始增量拉取 UP主 {up['name']} 的新视频")
                await self._incremental_refresh(up)
            except Exception as e:
                logger.error(f"刷新UP主视频失败 {up['name']}: {e}")

    async def _get_last_fetch_time(self, up_uid: int) -> datetime | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(func.max(UpVideo.fetched_at)).where(UpVideo.up_uid == up_uid)
            )
            return result.scalar_one_or_none()

    async def _full_refresh(self, up: dict):
        vlist = await _fetch_videos(up["uid"])
        async with get_db_session() as session:
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

    async def _incremental_refresh(self, up: dict, max_retries: int = 3, retry_delay: float = 10.0):
        ps = 50
        pn = 1
        new_count = 0
        consecutive_exists = 0
        max_consecutive_exists = 3
        has_found_new = False
        first_page = True

        while True:
            vlist, rate_limited, _ = await _fetch_videos_page(up["uid"], pn, ps)

            if rate_limited:
                if first_page:
                    logger.warning(f"第 1 页触发限流，跳过该UP主")
                    break
                if max_retries > 0:
                    logger.warning(f"触发限流，等待 {retry_delay} 秒后重试 (剩余重试次数: {max_retries})")
                    await asyncio.sleep(retry_delay)
                    max_retries -= 1
                    retry_delay *= 1.5
                    continue
                else:
                    logger.warning(f"重试次数用尽，停止拉取")
                    break

            if not vlist:
                logger.info(f"UP主 {up['name']} 视频列表为空，停止拉取")
                break

            page_has_new = False
            async with get_db_session() as session:
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
                        new_count += 1
                        page_has_new = True
                        consecutive_exists = 0
                    else:
                        consecutive_exists += 1

                if page_has_new:
                    await session.commit()
                    has_found_new = True
                    logger.info(f"第 {pn} 页：新增 {len(vlist)} 个新视频，累计 {new_count} 个")

            if pn == 1:
                first_page = False
            elif has_found_new and consecutive_exists >= max_consecutive_exists:
                logger.info(f"找到新视频后连续 {max_consecutive_exists} 页均为已有视频，停止拉取")
                break

            pn += 1
            await asyncio.sleep(1.5)

        logger.info(f"增量刷新 {up['name']} 完成：共新增 {new_count} 个视频")

    async def search(self, keyword: str, limit: int = 10) -> list[dict]:
        kw = keyword.strip().lower()
        async with get_db_session() as session:
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
