"""B站音乐客户端封装"""

import logging
from typing import Optional

import httpx
from bilibili_api import video, Credential

from apps.live.music.models import MusicItem

logger = logging.getLogger(__name__)


class BilibiliMusicClient:
    BV_REGEX = r"BV[a-zA-Z0-9]{10}"

    def __init__(self, sessdata: Optional[str] = None):
        self.sessdata = sessdata
        self._credential: Optional[Credential] = None
        if sessdata:
            self._credential = Credential(sessdata=sessdata)
        self._configure_bilibili_headers()

    @staticmethod
    def _configure_bilibili_headers() -> None:
        try:
            from bilibili_api import HEADERS
            HEADERS["Accept-Encoding"] = "identity"
        except Exception:
            pass

    async def get_video_info(self, bvid: str) -> Optional[dict]:
        try:
            v = video.Video(bvid=bvid, credential=self._credential)
            info = await v.get_info()
            return {
                "bvid": info.get("bvid"),
                "title": info.get("title"),
                "duration": info.get("duration", 0),
                "owner": info.get("owner", {}),
                "pic": info.get("pic"),
            }
        except Exception as e:
            logger.error(f"获取视频信息失败: {bvid}, error: {e}")
            return None

    async def get_audio_url(self, bvid: str) -> Optional[str]:
        try:
            v = video.Video(bvid=bvid, credential=self._credential)
            play_url = await v.get_download_url(page_index=0)
            dash = play_url.get("dash")
            if dash:
                audios = dash.get("audio")
                if audios:
                    best_audio = max(audios, key=lambda x: x.get("id", 0))
                    return best_audio.get("baseUrl")
            durl = play_url.get("durl")
            if durl and len(durl) > 0:
                return durl[0].get("url")
            return None
        except Exception as e:
            logger.error(f"获取音频URL失败: {bvid}, error: {e}")
            return None

    async def get_music_item_with_overrides(
        self, bvid: str, requestedBy: str, title: str = None, artist: str = None
    ) -> Optional[MusicItem]:
        info = await self.get_video_info(bvid)
        if not info:
            return None
        audioUrl = await self.get_audio_url(bvid)
        if not audioUrl:
            return None
        owner = info.get("owner", {})
        import uuid
        from datetime import datetime
        return MusicItem(
            id=str(uuid.uuid4()),
            bvid=info["bvid"],
            title=title or info["title"],
            upName=artist or owner.get("name", "未知UP主"),
            upFace=owner.get("face"),
            duration=info.get("duration", 0),
            audioUrl=audioUrl,
            coverUrl=info.get("pic", ""),
            requestedBy=requestedBy,
            requestedAt=datetime.now(),
        )

    @staticmethod
    def extract_bv(text: str) -> Optional[str]:
        import re
        match = re.search(BilibiliMusicClient.BV_REGEX, text)
        if match:
            return match.group(0)
        return None
