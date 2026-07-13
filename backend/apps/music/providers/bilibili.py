from __future__ import annotations

import html
import logging
import re
from urllib.parse import urlparse

from bilibili_api import Credential, search, video

from apps.config import config
from apps.music.models import AudioStream, ProviderSearchResult, Track
from apps.music.providers.base import ProviderTrustPolicy

logger = logging.getLogger(__name__)


class BilibiliMusicProvider:
    id = "bilibili"
    trust_policy = ProviderTrustPolicy.REVIEW_REQUIRED
    SOURCE_PATTERN = re.compile(r"BV[a-zA-Z0-9]{10}")

    def __init__(self) -> None:
        sessdata = config.bilibili_sessdata
        self._credential = Credential(sessdata=sessdata) if sessdata else None
        try:
            from bilibili_api import HEADERS

            HEADERS["Accept-Encoding"] = "identity"
        except (ImportError, TypeError):
            logger.debug("Unable to override bilibili-api Accept-Encoding", exc_info=True)

    @classmethod
    def extract_source_id(cls, text: str) -> str | None:
        match = cls.SOURCE_PATTERN.search(text)
        return match.group(0) if match else None

    async def search(self, query: str, limit: int = 10) -> list[ProviderSearchResult]:
        payload = await search.search_by_type(
            keyword=query,
            search_type=search.SearchObjectType.VIDEO,
            video_zone_type=3,
            page_size=min(max(limit, 1), 50),
        )
        rows = payload.get("result") or []
        results: list[ProviderSearchResult] = []
        for row in rows[:limit]:
            source_id = str(row.get("bvid") or "")
            if not source_id:
                continue
            title = re.sub(r"<[^>]+>", "", html.unescape(str(row.get("title") or "")))
            results.append(
                ProviderSearchResult(
                    source_id=source_id,
                    title=title,
                    artist=str(row.get("author") or ""),
                    duration_seconds=_parse_duration(row.get("duration")),
                    cover_url=_https_url(str(row.get("pic") or "")),
                    metadata={"tags": str(row.get("tag") or "")},
                )
            )
        return results

    async def inspect(self, source_id: str) -> Track:
        item = video.Video(bvid=source_id, credential=self._credential)
        info = await item.get_info()
        tags_payload = await item.get_tags()
        tags = [str(tag.get("tag_name") or "") for tag in tags_payload if tag.get("tag_name")]
        owner = info.get("owner") or {}
        pages = info.get("pages") or []
        return Track(
            provider=self.id,
            source_id=str(info.get("bvid") or source_id),
            title=str(info.get("title") or source_id),
            artists=[str(owner.get("name") or "未知UP主")],
            duration_seconds=int(info.get("duration") or 0),
            cover_url=_https_url(str(info.get("pic") or "")),
            metadata={
                "description": str(info.get("desc") or "")[:1000],
                "tid": int(info.get("tid") or 0),
                "tname": str(info.get("tname") or ""),
                "tags": tags,
                "owner_id": int(owner.get("mid") or 0),
                "view_count": int((info.get("stat") or {}).get("view") or 0),
                "pages": [
                    {
                        "cid": int(page.get("cid") or 0),
                        "page": int(page.get("page") or 0),
                        "part": str(page.get("part") or ""),
                        "duration": int(page.get("duration") or 0),
                    }
                    for page in pages
                ],
            },
        )

    async def resolve_stream(self, source_id: str) -> AudioStream:
        item = video.Video(bvid=source_id, credential=self._credential)
        payload = await item.get_download_url(page_index=0)
        audios = (payload.get("dash") or {}).get("audio") or []
        if audios:
            best = max(audios, key=lambda audio: int(audio.get("bandwidth") or 0))
            url = best.get("baseUrl") or best.get("base_url")
            if url:
                _validate_stream_url(str(url))
                return AudioStream(
                    url=str(url),
                    media_type=str(best.get("mimeType") or "audio/mp4"),
                    headers={
                        "Referer": "https://www.bilibili.com/",
                        "User-Agent": "Mozilla/5.0",
                    },
                    allowed_host_suffixes=["bilivideo.com", "bilibili.com"],
                )
        durl = payload.get("durl") or []
        if durl and durl[0].get("url"):
            _validate_stream_url(str(durl[0]["url"]))
            return AudioStream(
                url=str(durl[0]["url"]),
                headers={"Referer": "https://www.bilibili.com/", "User-Agent": "Mozilla/5.0"},
                allowed_host_suffixes=["bilivideo.com", "bilibili.com"],
            )
        raise RuntimeError(f"Bilibili video has no playable audio stream: {source_id}")


def _https_url(value: str) -> str:
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("http://"):
        return f"https://{value[7:]}"
    return value


def _parse_duration(value: object) -> int:
    if isinstance(value, int):
        return value
    parts = str(value or "0").split(":")
    try:
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + int(part)
        return seconds
    except ValueError:
        return 0


def _validate_stream_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not (
        host.endswith(".bilivideo.com")
        or host == "bilivideo.com"
        or host.endswith(".bilibili.com")
        or host == "bilibili.com"
    ):
        raise RuntimeError("Bilibili returned an untrusted audio stream URL")
