"""弹幕拦截和点歌服务"""

import logging
import re
from typing import Optional

from apps.music.client import BilibiliMusicClient
from apps.music.models import DanmakuInterceptResult, MusicItem
from apps.music.queue import get_music_queue
from apps.music.up_videos import get_up_video_manager

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

    async def process_danmaku(
        self, text: str, user: str
    ) -> DanmakuInterceptResult:
        if not self.is_music_request(text):
            return DanmakuInterceptResult(
                is_music_request=False, raw_text=text
            )
        bv = self.extract_bv(text)
        if not bv:
            song_name = self.extract_song_name(text)
            if not song_name:
                return DanmakuInterceptResult(
                    is_music_request=True,
                    raw_text=text,
                    error="未找到有效的BV号或歌名",
                )
            try:
                manager = get_up_video_manager()
                await manager.ensure_fetched()
                matches = await manager.search(song_name)
                if matches:
                    best_match = matches[0]
                    bv = best_match["bvid"]
                    logger.info(f"歌名匹配成功: '{song_name}' -> {best_match['title']} ({bv})")
                else:
                    return DanmakuInterceptResult(
                        is_music_request=True,
                        raw_text=text,
                        error=f"未找到匹配的歌曲: {song_name}",
                    )
            except Exception as e:
                logger.error(f"搜索UP主视频失败: {e}")
                return DanmakuInterceptResult(
                    is_music_request=True,
                    raw_text=text,
                    error="搜索失败，请稍后重试",
                )
        try:
            music_item = await self._client.get_music_item(bv, user)
            if not music_item:
                return DanmakuInterceptResult(
                    is_music_request=True,
                    raw_text=text,
                    error="获取音乐信息失败，视频可能不存在或已被删除",
                )
            queue = get_music_queue()
            await queue.add(music_item)
            logger.info(f"点歌成功: {music_item.title} by {user}")
            return DanmakuInterceptResult(
                is_music_request=True,
                music_item=music_item,
                raw_text=text,
            )
        except Exception as e:
            logger.error(f"处理点歌请求失败: {e}")
            return DanmakuInterceptResult(
                is_music_request=True,
                raw_text=text,
                error=f"处理失败: {str(e)}",
            )


_danmaku_service: Optional[DanmakuMusicService] = None


def get_danmaku_service(sessdata: Optional[str] = None) -> DanmakuMusicService:
    global _danmaku_service
    if _danmaku_service is None:
        _danmaku_service = DanmakuMusicService(sessdata=sessdata)
    return _danmaku_service
