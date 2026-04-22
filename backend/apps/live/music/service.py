"""弹幕拦截和点歌服务"""

import logging
import re
from typing import Optional

from sqlalchemy import select

from apps.config import config
from apps.db import get_db_session, PlaylistItem
from apps.live.music.client import BilibiliMusicClient
from apps.live.music.library import get_playlist_manager
from apps.live.music.llm_verify import get_llm_verifier
from apps.live.music.models import DanmakuInterceptResult, MusicItem
from apps.live.music.queue import get_music_queue
from apps.live.music.up_videos import get_up_video_manager

logger = logging.getLogger(__name__)

DANMAKU_PREFIXES = ["点歌", "点歌 ", "来一首", "来一首 ", "播放", "播放 "]
BV_PATTERN = r"BV[a-zA-Z0-9]{10}"


class DanmakuMusicService:
    def __init__(self, sessdata: Optional[str] = None):
        self._client = BilibiliMusicClient(sessdata=sessdata)

    @staticmethod
    def is_music_request(text: str) -> bool:
        text_lower = text.lower().strip()
        for prefix in DANMAKU_PREFIXES:
            if text_lower.startswith(prefix.lower()):
                return True
        if re.search(BV_PATTERN, text):
            return True
        return False

    @staticmethod
    def extract_bv(text: str) -> Optional[str]:
        match = re.search(BV_PATTERN, text)
        if match:
            return match.group(0)
        for prefix in DANMAKU_PREFIXES:
            text = text.replace(prefix, "").strip()
            text = text.replace(prefix.replace(" ", ""), "").strip()
        match = re.search(BV_PATTERN, text)
        if match:
            return match.group(0)
        return None

    @staticmethod
    def extract_song_name(text: str) -> str:
        name = text.strip()
        for prefix in DANMAKU_PREFIXES:
            if name.lower().startswith(prefix.lower()):
                name = name[len(prefix):].strip()
                break
        bv_match = re.search(BV_PATTERN, name)
        if bv_match:
            name = name[:bv_match.start()] + name[bv_match.end():]
        return name.strip()

    async def _search_playlist(self, keyword: str) -> Optional[dict]:
        library = get_playlist_manager()
        await library.initialize()
        kw = keyword.strip().lower()
        async with get_db_session() as session:
            result = await session.execute(
                select(PlaylistItem).where(PlaylistItem.enabled == True)
            )
            items = result.scalars().all()
            for item in items:
                title_lower = item.title.lower()
                artist_lower = (item.artist or "").lower()
                bvid_lower = item.bvid.lower()
                if kw in title_lower or kw in artist_lower or kw in bvid_lower or title_lower in kw or kw in bvid_lower:
                    logger.info(f"在预备歌单中找到匹配: {item.title} ({item.bvid})")
                    return {"bvid": item.bvid, "title": item.title, "artist": item.artist or ""}
            return None

    async def _search_up_videos(self, song_name: str) -> Optional[str]:
        manager = get_up_video_manager()
        await manager.ensure_fetched()
        matches = await manager.search(song_name)
        if matches:
            best_match = matches[0]
            bv = best_match["bvid"]
            logger.info(f"在UP主视频中找到匹配: '{song_name}' -> {best_match['title']} ({bv})")
            return bv
        return None

    async def _llm_verify_and_collect(self, bvid: str, user: str) -> tuple[Optional[dict], Optional[MusicItem]]:
        verifier = get_llm_verifier()
        verify_result = await verifier.verify(bvid)
        if verify_result is None:
            logger.warning(f"LLM验证失败，拒绝播放: {bvid}")
            return None, None
        if not verify_result.is_music:
            logger.info(f"LLM判定非音乐视频: {bvid}, 原因: {verify_result.reason}")
            return {"is_music": False, "reason": verify_result.reason}, None
        music_item = await self._client.get_music_item_with_overrides(
            bvid, user,
            title=verify_result.song_name,
            artist=verify_result.artist
        )
        if not music_item:
            return {"is_music": False, "reason": "获取音频URL失败"}, None
        llm_info = {
            "is_music": True,
            "song_name": verify_result.song_name,
            "artist": verify_result.artist,
            "reason": verify_result.reason,
        }
        try:
            video_detail = await verifier._get_video_detail(bvid)
            if video_detail and video_detail.get("view_count", 0) >= config.auto_collect_min_views:
                library = get_playlist_manager()
                existing = await library.add(bvid=bvid, title=verify_result.song_name, artist=verify_result.artist)
                if existing:
                    logger.info(f"自动收录到预备歌单: {verify_result.song_name} - {verify_result.artist} (播放量{video_detail['view_count']})")
        except Exception as e:
            logger.error(f"自动收录失败: {e}")
        return llm_info, music_item

    async def process_danmaku(self, text: str, user: str) -> DanmakuInterceptResult:
        if not self.is_music_request(text):
            return DanmakuInterceptResult(isMusicRequest=False, rawText=text)
        queue = get_music_queue()
        user_count = await queue.count_user_requests(user)
        if user_count >= 2:
            return DanmakuInterceptResult(isMusicRequest=True, rawText=text, error=f"你已有{user_count}首歌在队列中，请等待播放完成后再点歌")
        queue_length = len(await queue.get_queue())
        current = await queue.get_current()
        total = queue_length + (1 if current else 0)
        if total >= 5:
            return DanmakuInterceptResult(isMusicRequest=True, rawText=text, error="播放队列已满(最多5首)，请稍后再试")
        bv = self.extract_bv(text)
        playlist_match = None
        song_name = ""
        if bv:
            playlist_match = await self._search_playlist(bv)
            if playlist_match:
                bv = playlist_match["bvid"]
        else:
            song_name = self.extract_song_name(text)
            if not song_name:
                return DanmakuInterceptResult(isMusicRequest=True, rawText=text, error="未找到有效的BV号或歌名")
            playlist_match = await self._search_playlist(song_name)
            if playlist_match:
                bv = playlist_match["bvid"]
            else:
                found_bv = await self._search_up_videos(song_name)
                if found_bv:
                    bv = found_bv
                else:
                    return DanmakuInterceptResult(isMusicRequest=True, rawText=text, error=f"未找到匹配的歌曲: {song_name}")
        if not bv:
            return DanmakuInterceptResult(isMusicRequest=True, rawText=text, error="无法确定BV号")
        try:
            if playlist_match:
                music_item = await self._client.get_music_item_with_overrides(
                    bv, user,
                    title=playlist_match.get("title"),
                    artist=playlist_match.get("artist")
                )
                if not music_item:
                    return DanmakuInterceptResult(isMusicRequest=True, rawText=text, error="获取音频URL失败")
                logger.info(f"点歌成功(预备歌单): {music_item.title} by {user}")
            else:
                llm_info, music_item = await self._llm_verify_and_collect(bv, user)
                if not music_item:
                    error_msg = llm_info.get("reason", "获取音乐信息失败") if llm_info else "获取音乐信息失败"
                    return DanmakuInterceptResult(isMusicRequest=True, rawText=text, error=error_msg)
                logger.info(f"点歌成功(LLM验证): {music_item.title} by {user}")
            await queue.add(music_item)
            return DanmakuInterceptResult(isMusicRequest=True, musicItem=music_item, rawText=text)
        except Exception as e:
            logger.error(f"处理点歌请求失败: {e}")
            return DanmakuInterceptResult(isMusicRequest=True, rawText=text, error=f"处理失败: {str(e)}")


_danmaku_service: Optional[DanmakuMusicService] = None


def get_danmaku_service(sessdata: Optional[str] = None) -> DanmakuMusicService:
    global _danmaku_service
    if _danmaku_service is None:
        _danmaku_service = DanmakuMusicService(sessdata=sessdata)
    return _danmaku_service
